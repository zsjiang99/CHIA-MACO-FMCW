/*
 * Fixed-shape, source-unrolled views of the FMCW hotspots for CGRA mapping.
 *
 * The end-to-end numerical reference remains in fmcw.c. These functions expose
 * one explicit steady-state loop per stage with lane-level tail guards.
 */

#include "fmcw.h"

#ifndef FMCW_UNROLL_FACTOR
#define FMCW_UNROLL_FACTOR 1
#endif

#if FMCW_UNROLL_FACTOR < 1 || FMCW_UNROLL_FACTOR > 6
#error "FMCW_UNROLL_FACTOR must be between 1 and 6"
#endif

static inline void window_element(
    const float *input_real,
    const float *input_imag,
    const float *window,
    float *output_real,
    float *output_imag,
    int index) {
    if (index < FMCW_RANGE_BINS) {
        output_real[index] = input_real[index] * window[index];
        output_imag[index] = input_imag[index] * window[index];
    }
}

void fmcw_window_map(
    const float *input_real,
    const float *input_imag,
    const float *window,
    float *output_real,
    float *output_imag) {
    for (int base = 0; base < FMCW_RANGE_BINS;
         base += FMCW_UNROLL_FACTOR) {
        window_element(input_real, input_imag, window, output_real, output_imag, base);
#if FMCW_UNROLL_FACTOR >= 2
        window_element(input_real, input_imag, window, output_real, output_imag, base + 1);
#endif
#if FMCW_UNROLL_FACTOR >= 3
        window_element(input_real, input_imag, window, output_real, output_imag, base + 2);
#endif
#if FMCW_UNROLL_FACTOR >= 4
        window_element(input_real, input_imag, window, output_real, output_imag, base + 3);
#endif
#if FMCW_UNROLL_FACTOR >= 5
        window_element(input_real, input_imag, window, output_real, output_imag, base + 4);
#endif
#if FMCW_UNROLL_FACTOR >= 6
        window_element(input_real, input_imag, window, output_real, output_imag, base + 5);
#endif
    }
}

static inline void fft_butterfly(
    float *data_real,
    float *data_imag,
    const float *twiddle_real,
    const float *twiddle_imag,
    int offset) {
    if (offset >= FMCW_RANGE_BINS / 2)
        return;
    const int odd = offset + FMCW_RANGE_BINS / 2;
    const float odd_real = data_real[odd];
    const float odd_imag = data_imag[odd];
    const float product_real =
        twiddle_real[offset] * odd_real - twiddle_imag[offset] * odd_imag;
    const float product_imag =
        twiddle_real[offset] * odd_imag + twiddle_imag[offset] * odd_real;
    const float even_real = data_real[offset];
    const float even_imag = data_imag[offset];
    data_real[offset] = even_real + product_real;
    data_imag[offset] = even_imag + product_imag;
    data_real[odd] = even_real - product_real;
    data_imag[odd] = even_imag - product_imag;
}

void fmcw_fft_stage_map(
    float *data_real,
    float *data_imag,
    const float *twiddle_real,
    const float *twiddle_imag) {
    for (int base = 0; base < FMCW_RANGE_BINS / 2;
         base += FMCW_UNROLL_FACTOR) {
        fft_butterfly(data_real, data_imag, twiddle_real, twiddle_imag, base);
#if FMCW_UNROLL_FACTOR >= 2
        fft_butterfly(data_real, data_imag, twiddle_real, twiddle_imag, base + 1);
#endif
#if FMCW_UNROLL_FACTOR >= 3
        fft_butterfly(data_real, data_imag, twiddle_real, twiddle_imag, base + 2);
#endif
#if FMCW_UNROLL_FACTOR >= 4
        fft_butterfly(data_real, data_imag, twiddle_real, twiddle_imag, base + 3);
#endif
#if FMCW_UNROLL_FACTOR >= 5
        fft_butterfly(data_real, data_imag, twiddle_real, twiddle_imag, base + 4);
#endif
#if FMCW_UNROLL_FACTOR >= 6
        fft_butterfly(data_real, data_imag, twiddle_real, twiddle_imag, base + 5);
#endif
    }
}

static inline void transpose_element(
    const float *input, float *output, int row, int column) {
    if (column < FMCW_RANGE_BINS)
        output[column * FMCW_DOPPLER_BINS + row] =
            input[row * FMCW_RANGE_BINS + column];
}

void fmcw_transpose_map(const float *input, float *output, int row) {
    for (int base = 0; base < FMCW_RANGE_BINS;
         base += FMCW_UNROLL_FACTOR) {
        transpose_element(input, output, row, base);
#if FMCW_UNROLL_FACTOR >= 2
        transpose_element(input, output, row, base + 1);
#endif
#if FMCW_UNROLL_FACTOR >= 3
        transpose_element(input, output, row, base + 2);
#endif
#if FMCW_UNROLL_FACTOR >= 4
        transpose_element(input, output, row, base + 3);
#endif
#if FMCW_UNROLL_FACTOR >= 5
        transpose_element(input, output, row, base + 4);
#endif
#if FMCW_UNROLL_FACTOR >= 6
        transpose_element(input, output, row, base + 5);
#endif
    }
}

static inline void power_channel(
    const float *cube_real,
    const float *cube_imag,
    float *sum,
    int bins_per_channel,
    int bin,
    int channel) {
    if (channel < FMCW_RX_CHANNELS) {
        const int index = channel * bins_per_channel + bin;
        const float real = cube_real[index];
        const float imag = cube_imag[index];
        *sum += real * real + imag * imag;
    }
}

void fmcw_accumulate_power_map(
    const float *cube_real,
    const float *cube_imag,
    float *power,
    int bins_per_channel,
    int bin) {
    float sum = 0.0f;
    for (int base = 0; base < FMCW_RX_CHANNELS;
         base += FMCW_UNROLL_FACTOR) {
        power_channel(cube_real, cube_imag, &sum, bins_per_channel, bin, base);
#if FMCW_UNROLL_FACTOR >= 2
        power_channel(cube_real, cube_imag, &sum, bins_per_channel, bin, base + 1);
#endif
#if FMCW_UNROLL_FACTOR >= 3
        power_channel(cube_real, cube_imag, &sum, bins_per_channel, bin, base + 2);
#endif
#if FMCW_UNROLL_FACTOR >= 4
        power_channel(cube_real, cube_imag, &sum, bins_per_channel, bin, base + 3);
#endif
#if FMCW_UNROLL_FACTOR >= 5
        power_channel(cube_real, cube_imag, &sum, bins_per_channel, bin, base + 4);
#endif
#if FMCW_UNROLL_FACTOR >= 6
        power_channel(cube_real, cube_imag, &sum, bins_per_channel, bin, base + 5);
#endif
    }
    power[bin] = sum;
}

static inline void cfar_neighbor(
    const float *power,
    float *training_sum,
    int *training_cells,
    int center,
    int columns,
    int delta_row,
    int slot) {
    if (slot < 11) {
        const int delta_column = slot - 5;
        const int inside_guard =
            delta_row >= -1 && delta_row <= 1 &&
            delta_column >= -1 && delta_column <= 1;
        if (!inside_guard) {
            *training_sum += power[center + delta_row * columns + delta_column];
            ++*training_cells;
        }
    }
}

void fmcw_cfar_2d_map(
    const float *power,
    float *training_sum,
    int *training_cells,
    int center,
    int columns,
    int delta_row) {
    for (int base = 0; base < 11; base += FMCW_UNROLL_FACTOR) {
        cfar_neighbor(
            power, training_sum, training_cells, center, columns, delta_row, base);
#if FMCW_UNROLL_FACTOR >= 2
        cfar_neighbor(
            power, training_sum, training_cells, center, columns, delta_row, base + 1);
#endif
#if FMCW_UNROLL_FACTOR >= 3
        cfar_neighbor(
            power, training_sum, training_cells, center, columns, delta_row, base + 2);
#endif
#if FMCW_UNROLL_FACTOR >= 4
        cfar_neighbor(
            power, training_sum, training_cells, center, columns, delta_row, base + 3);
#endif
#if FMCW_UNROLL_FACTOR >= 5
        cfar_neighbor(
            power, training_sum, training_cells, center, columns, delta_row, base + 4);
#endif
#if FMCW_UNROLL_FACTOR >= 6
        cfar_neighbor(
            power, training_sum, training_cells, center, columns, delta_row, base + 5);
#endif
    }
}
