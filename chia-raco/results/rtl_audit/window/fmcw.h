#ifndef CHIA_MACO_FMCW_H
#define CHIA_MACO_FMCW_H

#include <stdint.h>

#define FMCW_RANGE_BINS 256
#define FMCW_DOPPLER_BINS 128
#define FMCW_RX_CHANNELS 4

void fmcw_window(
    const float *input_real,
    const float *input_imag,
    const float *window,
    float *output_real,
    float *output_imag,
    int length);

void fmcw_fft_stage(
    float *data_real,
    float *data_imag,
    const float *twiddle_real,
    const float *twiddle_imag,
    int length,
    int butterfly_size);

void fmcw_fft(
    float *data_real,
    float *data_imag,
    const float *twiddle_real,
    const float *twiddle_imag,
    int length);

void fmcw_transpose(
    const float *input,
    float *output,
    int rows,
    int columns);

void fmcw_accumulate_power(
    const float *cube_real,
    const float *cube_imag,
    float *power,
    int channels,
    int bins_per_channel);

void fmcw_cfar_2d(
    const float *power,
    uint8_t *detections,
    int rows,
    int columns,
    int training_radius,
    int guard_radius,
    float threshold_scale);

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
    uint8_t *detections);

#endif

