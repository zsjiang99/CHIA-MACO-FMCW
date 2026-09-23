#include "fmcw.h"

#include <stddef.h>

#ifndef FMCW_UNROLL_FACTOR
#define FMCW_UNROLL_FACTOR 1
#endif

#if defined(__clang__) && FMCW_UNROLL_FACTOR > 1
#define FMCW_PRAGMA_EXPAND_(value) _Pragma(#value)
#define FMCW_PRAGMA_EXPAND(value) FMCW_PRAGMA_EXPAND_(value)
#define FMCW_UNROLL_LOOP \
    FMCW_PRAGMA_EXPAND(clang loop unroll_count(FMCW_UNROLL_FACTOR))
#else
#define FMCW_UNROLL_LOOP
#endif

static void fmcw_swap(float *left, float *right) {
    const float temporary = *left;
    *left = *right;
    *right = temporary;
}

static void fmcw_bit_reverse(float *data_real, float *data_imag, int length) {
    int reversed = 0;

    for (int index = 1; index < length; ++index) {
        int bit = length >> 1;
        while (reversed & bit) {
            reversed ^= bit;
            bit >>= 1;
        }
        reversed ^= bit;

        if (index < reversed) {
            fmcw_swap(&data_real[index], &data_real[reversed]);
            fmcw_swap(&data_imag[index], &data_imag[reversed]);
        }
    }
}

void fmcw_window(
    const float *input_real,
    const float *input_imag,
    const float *window,
    float *output_real,
    float *output_imag,
    int length) {
    FMCW_UNROLL_LOOP
    for (int index = 0; index < length; ++index) {
        output_real[index] = input_real[index] * window[index];
        output_imag[index] = input_imag[index] * window[index];
    }
}

void fmcw_fft_stage(
    float *data_real,
    float *data_imag,
    const float *twiddle_real,
    const float *twiddle_imag,
    int length,
    int butterfly_size) {
    const int half_size = butterfly_size >> 1;
    const int twiddle_step = length / butterfly_size;

    for (int group = 0; group < length; group += butterfly_size) {
        FMCW_UNROLL_LOOP
        for (int offset = 0; offset < half_size; ++offset) {
            const int even = group + offset;
            const int odd = even + half_size;
            const int twiddle = offset * twiddle_step;
            const float odd_real = data_real[odd];
            const float odd_imag = data_imag[odd];
            const float product_real =
                twiddle_real[twiddle] * odd_real -
                twiddle_imag[twiddle] * odd_imag;
            const float product_imag =
                twiddle_real[twiddle] * odd_imag +
                twiddle_imag[twiddle] * odd_real;
            const float even_real = data_real[even];
            const float even_imag = data_imag[even];

            data_real[even] = even_real + product_real;
            data_imag[even] = even_imag + product_imag;
            data_real[odd] = even_real - product_real;
            data_imag[odd] = even_imag - product_imag;
        }
    }
}

void fmcw_fft(
    float *data_real,
    float *data_imag,
    const float *twiddle_real,
    const float *twiddle_imag,
    int length) {
    fmcw_bit_reverse(data_real, data_imag, length);
    for (int butterfly_size = 2;
         butterfly_size <= length;
         butterfly_size <<= 1) {
        fmcw_fft_stage(
            data_real,
            data_imag,
            twiddle_real,
            twiddle_imag,
            length,
            butterfly_size);
    }
}

void fmcw_transpose(
    const float *input,
    float *output,
    int rows,
    int columns) {
    for (int row = 0; row < rows; ++row) {
        FMCW_UNROLL_LOOP
        for (int column = 0; column < columns; ++column) {
            output[column * rows + row] = input[row * columns + column];
        }
    }
}

void fmcw_accumulate_power(
    const float *cube_real,
    const float *cube_imag,
    float *power,
    int channels,
    int bins_per_channel) {
    for (int bin = 0; bin < bins_per_channel; ++bin) {
        float sum = 0.0f;
        FMCW_UNROLL_LOOP
        for (int channel = 0; channel < channels; ++channel) {
            const int index = channel * bins_per_channel + bin;
            const float real = cube_real[index];
            const float imag = cube_imag[index];
            sum += real * real + imag * imag;
        }
        power[bin] = sum;
    }
}

void fmcw_cfar_2d(
    const float *power,
    uint8_t *detections,
    int rows,
    int columns,
    int training_radius,
    int guard_radius,
    float threshold_scale) {
    const int outer_radius = training_radius + guard_radius;

    for (int row = 0; row < rows; ++row) {
        for (int column = 0; column < columns; ++column) {
            float training_sum = 0.0f;
            int training_cells = 0;

            if (row < outer_radius || row >= rows - outer_radius ||
                column < outer_radius || column >= columns - outer_radius) {
                detections[row * columns + column] = 0;
                continue;
            }

            for (int delta_row = -outer_radius;
                 delta_row <= outer_radius;
                 ++delta_row) {
                FMCW_UNROLL_LOOP
                for (int delta_column = -outer_radius;
                     delta_column <= outer_radius;
                     ++delta_column) {
                    const int inside_guard =
                        delta_row >= -guard_radius &&
                        delta_row <= guard_radius &&
                        delta_column >= -guard_radius &&
                        delta_column <= guard_radius;
                    if (!inside_guard) {
                        const int neighbor =
                            (row + delta_row) * columns + column + delta_column;
                        training_sum += power[neighbor];
                        ++training_cells;
                    }
                }
            }

            const float noise = training_sum / (float)training_cells;
            detections[row * columns + column] =
                power[row * columns + column] > threshold_scale * noise;
        }
    }
}

void fmcw_pipeline(
    const float *adc_real,
    const float *adc_imag,
    const float *window,
    const float *range_twiddle_real,
    const float *range_twiddle_imag,
    const float *doppler_twiddle_real,
    const float *doppler_twiddle_imag,
    float *range_cube_real,
    float *range_cube_imag,
    float *doppler_cube_real,
    float *doppler_cube_imag,
    float *power,
    uint8_t *detections) {
    const int range_plane = FMCW_DOPPLER_BINS * FMCW_RANGE_BINS;
    const int doppler_plane = FMCW_RANGE_BINS * FMCW_DOPPLER_BINS;

    for (int channel = 0; channel < FMCW_RX_CHANNELS; ++channel) {
        for (int chirp = 0; chirp < FMCW_DOPPLER_BINS; ++chirp) {
            const int base =
                (channel * FMCW_DOPPLER_BINS + chirp) * FMCW_RANGE_BINS;
            fmcw_window(
                &adc_real[base],
                &adc_imag[base],
                window,
                &range_cube_real[base],
                &range_cube_imag[base],
                FMCW_RANGE_BINS);
            fmcw_fft(
                &range_cube_real[base],
                &range_cube_imag[base],
                range_twiddle_real,
                range_twiddle_imag,
                FMCW_RANGE_BINS);
        }

        const int range_offset = channel * range_plane;
        const int doppler_offset = channel * doppler_plane;
        fmcw_transpose(
            &range_cube_real[range_offset],
            &doppler_cube_real[doppler_offset],
            FMCW_DOPPLER_BINS,
            FMCW_RANGE_BINS);
        fmcw_transpose(
            &range_cube_imag[range_offset],
            &doppler_cube_imag[doppler_offset],
            FMCW_DOPPLER_BINS,
            FMCW_RANGE_BINS);

        for (int range = 0; range < FMCW_RANGE_BINS; ++range) {
            const int base = doppler_offset + range * FMCW_DOPPLER_BINS;
            fmcw_fft(
                &doppler_cube_real[base],
                &doppler_cube_imag[base],
                doppler_twiddle_real,
                doppler_twiddle_imag,
                FMCW_DOPPLER_BINS);
        }
    }

    fmcw_accumulate_power(
        doppler_cube_real,
        doppler_cube_imag,
        power,
        FMCW_RX_CHANNELS,
        doppler_plane);
    fmcw_cfar_2d(
        power,
        detections,
        FMCW_RANGE_BINS,
        FMCW_DOPPLER_BINS,
        4,
        1,
        6.0f);
}
