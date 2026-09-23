#include "fmcw.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define FMCW_PI 3.14159265358979323846

static void fill_twiddles(float *real, float *imag, int length) {
    for (int index = 0; index < length / 2; ++index) {
        const double angle = -2.0 * FMCW_PI * (double)index / (double)length;
        real[index] = (float)cos(angle);
        imag[index] = (float)sin(angle);
    }
}

static void fill_scene(float *adc_real, float *adc_imag) {
    const int target_range = 17;
    const int target_doppler = 9;

    for (int channel = 0; channel < FMCW_RX_CHANNELS; ++channel) {
        const double channel_phase = 0.17 * (double)channel;
        for (int chirp = 0; chirp < FMCW_DOPPLER_BINS; ++chirp) {
            for (int sample = 0; sample < FMCW_RANGE_BINS; ++sample) {
                const double angle =
                    2.0 * FMCW_PI *
                        ((double)target_range * (double)sample /
                             (double)FMCW_RANGE_BINS +
                         (double)target_doppler * (double)chirp /
                             (double)FMCW_DOPPLER_BINS) +
                    channel_phase;
                const int index =
                    (channel * FMCW_DOPPLER_BINS + chirp) *
                        FMCW_RANGE_BINS +
                    sample;
                adc_real[index] = (float)cos(angle);
                adc_imag[index] = (float)sin(angle);
            }
        }
    }
}

static void *checked_calloc(size_t count, size_t size) {
    void *memory = calloc(count, size);
    if (memory == NULL) {
        fprintf(stderr, "allocation failed\n");
        exit(2);
    }
    return memory;
}

int main(void) {
    const int samples =
        FMCW_RX_CHANNELS * FMCW_DOPPLER_BINS * FMCW_RANGE_BINS;
    const int bins = FMCW_RANGE_BINS * FMCW_DOPPLER_BINS;
    float *adc_real = checked_calloc((size_t)samples, sizeof(float));
    float *adc_imag = checked_calloc((size_t)samples, sizeof(float));
    float *window = checked_calloc(FMCW_RANGE_BINS, sizeof(float));
    float *range_twiddle_real =
        checked_calloc(FMCW_RANGE_BINS / 2, sizeof(float));
    float *range_twiddle_imag =
        checked_calloc(FMCW_RANGE_BINS / 2, sizeof(float));
    float *doppler_twiddle_real =
        checked_calloc(FMCW_DOPPLER_BINS / 2, sizeof(float));
    float *doppler_twiddle_imag =
        checked_calloc(FMCW_DOPPLER_BINS / 2, sizeof(float));
    float *range_cube_real = checked_calloc((size_t)samples, sizeof(float));
    float *range_cube_imag = checked_calloc((size_t)samples, sizeof(float));
    float *doppler_cube_real = checked_calloc((size_t)samples, sizeof(float));
    float *doppler_cube_imag = checked_calloc((size_t)samples, sizeof(float));
    float *power = checked_calloc((size_t)bins, sizeof(float));
    uint8_t *detections = checked_calloc((size_t)bins, sizeof(uint8_t));

    for (int index = 0; index < FMCW_RANGE_BINS; ++index) {
        window[index] = (float)(
            0.5 - 0.5 * cos(2.0 * FMCW_PI * (double)index /
                            (double)(FMCW_RANGE_BINS - 1)));
    }
    fill_twiddles(
        range_twiddle_real, range_twiddle_imag, FMCW_RANGE_BINS);
    fill_twiddles(
        doppler_twiddle_real, doppler_twiddle_imag, FMCW_DOPPLER_BINS);
    fill_scene(adc_real, adc_imag);

    fmcw_pipeline(
        adc_real,
        adc_imag,
        window,
        range_twiddle_real,
        range_twiddle_imag,
        doppler_twiddle_real,
        doppler_twiddle_imag,
        range_cube_real,
        range_cube_imag,
        doppler_cube_real,
        doppler_cube_imag,
        power,
        detections);

    int maximum_index = 0;
    int detection_count = 0;
    double power_sum = 0.0;
    for (int index = 0; index < bins; ++index) {
        power_sum += power[index];
        detection_count += detections[index] != 0;
        if (power[index] > power[maximum_index]) {
            maximum_index = index;
        }
    }

    const int peak_range = maximum_index / FMCW_DOPPLER_BINS;
    const int peak_doppler = maximum_index % FMCW_DOPPLER_BINS;
    printf(
        "{\"peak_range\":%d,\"peak_doppler\":%d,"
        "\"detections\":%d,\"power_sum\":%.9g}\n",
        peak_range,
        peak_doppler,
        detection_count,
        power_sum);

    free(adc_real);
    free(adc_imag);
    free(window);
    free(range_twiddle_real);
    free(range_twiddle_imag);
    free(doppler_twiddle_real);
    free(doppler_twiddle_imag);
    free(range_cube_real);
    free(range_cube_imag);
    free(doppler_cube_real);
    free(doppler_cube_imag);
    free(power);
    free(detections);

    return peak_range == 17 && peak_doppler == 9 && detection_count > 0
               ? 0
               : 1;
}

