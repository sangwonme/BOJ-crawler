#ifndef MXNET_OPERATOR_NEW_FORWARD_CUH_
#define MXNET_OPERATOR_NEW_FORWARD_CUH_

#include <mxnet/base.h>
#include <iostream>
#include <cmath>

namespace mxnet
{
namespace op
{

#define TILE_WIDTH 32
#define LOG2_TILE_WIDTH 5
#define PI 3.141592654f
#define B_SUB 1000
#define MINI_B 125
#define NUM_STREAMS 8

#define CHECK_CUDA(call) \
    do { \
        cudaError_t err = call; \
        if (err != cudaSuccess) { \
            std::cerr << "CUDA Error: " << cudaGetErrorString(err) << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
            exit(EXIT_FAILURE); \
        } \
    } while (0)

// 1. Padding Kernel
__global__ void pad_input_kernel(const float* input, float2* padded_input, 
                                 int B, int C, int H, int W, 
                                 int K, int stride, int T_in, int T_pad, 
                                 int tiles_h, int tiles_w) {
    // Determine tile indices from blockIdx
    int tile_h = blockIdx.y;
    int tile_w = blockIdx.x;

    // Determine thread indices within the tile
    int thread_h = threadIdx.y;
    int thread_w = threadIdx.x;

    // Calculate index of the input to load
    int h_in = tile_h * stride + thread_h;
    int w_in = tile_w * stride + thread_w;

    int b = blockIdx.z / C;
    int c = blockIdx.z % C;

    // Calculate padded input index
    int padded_idx = b * (C * tiles_h * tiles_w * T_pad * T_pad) + 
                        c * (tiles_h * tiles_w * T_pad * T_pad) + 
                        tile_h * (tiles_w * T_pad * T_pad) + 
                        tile_w * (T_pad * T_pad) + 
                        thread_h * T_pad + thread_w;

    // Check if within the real data region
    if (thread_h < T_in && thread_w < T_in && 
        h_in < H && w_in < W) {
        int input_idx = b * (C * H * W) + 
                        c * (H * W) + 
                        h_in * W + w_in;
        padded_input[padded_idx].x = input[input_idx];
        padded_input[padded_idx].y = 0.0f; // Imaginary part
    }
    else {
        padded_input[padded_idx].x = 0.0f;
        padded_input[padded_idx].y = 0.0f;
    }
}

// 2. Kernel Flipping
__global__ void flip_kernel_spatial(const float* kernel, float* flipped_kernel, int M, int C, int K) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int total_elements = M * C * K * K;

    if (tid >= total_elements) return;

    int m = tid / (C * K * K);
    int c = (tid / (K * K)) % C;
    int h = (tid / K) % K;
    int w = tid % K;

    int flipped_h = K - 1 - h;
    int flipped_w = K - 1 - w;

    int flipped_idx = m * (C * K * K) + c * (K * K) + flipped_h * K + flipped_w;
    flipped_kernel[flipped_idx] = kernel[tid];
}

// 2. Flipped Kernel Padding
__global__ void pad_flipped_kernel(const float* flipped_kernel, float2* padded_kernel, 
                                       int M, int C, int K, int T_pad) {
    int m = blockIdx.x;
    int c = blockIdx.y;

    // 2D thread indices within the padded kernel
    int thread_h = threadIdx.y;
    int thread_w = threadIdx.x;

    // Calculate padded index
    if (thread_h < T_pad && thread_w < T_pad) {
        if (thread_h < K && thread_w < K) {
            int idx = m * (C * K * K) + c * (K * K) + thread_h * K + thread_w;
            int padded_idx = m * (C * T_pad * T_pad) + c * (T_pad * T_pad) + thread_h * T_pad + thread_w;
            padded_kernel[padded_idx].x = flipped_kernel[idx];
            padded_kernel[padded_idx].y = 0.0f;
        }
        else {
            // Zero padding
            int padded_idx = m * (C * T_pad * T_pad) + c * (T_pad * T_pad) + thread_h * T_pad + thread_w;
            padded_kernel[padded_idx].x = 0.0f;
            padded_kernel[padded_idx].y = 0.0f;
        }
    }
}

__device__ inline void Butterfly(float2* a, float2* b, float2 w)
{
    float2 u = *a;
    float2 v;
    v.x = b->x * w.x - b->y * w.y;
    v.y = b->x * w.y + b->y * w.x;

    // Update the butterfly pair
    a->x = u.x + v.x;
    a->y = u.y + v.y;
    b->x = u.x - v.x;
    b->y = u.y - v.y;
}

__constant__ float2 twiddle_factors[TILE_WIDTH * LOG2_TILE_WIDTH]; // For a 32-point FFT

__device__ inline void InnerFFT_row(int mode, int row, int rowLen, float2* d_shared_1, float2* d_shared_2, bool bit_reverse)
{
    int tid = threadIdx.x;

    // Perform FFT stages
    for (int len = 2; len <= rowLen; len <<= 1)
    {
        int stride = len >> 1;               // Distance between butterfly pairs
        // int twiddle_idx = tid & (stride - 1);     // Twiddle factor index (equivalent to tid % stride)

        // Compute the twiddle factor
        // float two_times_inv_len = divide_by_pow2(2.0f, __ffs(len) - 1); // Precompute 2.0 / len
        // float ang = PI * twiddle_idx * two_times_inv_len;
        // float ang = (2.0f * PI * twiddle_idx) / len;
        // float2 w;
        // w.x = (mode == 0) ? __cosf(-ang) : __cosf(ang); // Forward or inverse FFT
        // w.y = (mode == 0) ? __sinf(-ang) : __sinf(ang);
        
        int stage = __ffs(len) - 2; // Stage index (0-based)
        int base_offset = (1 << stage) - 1; // Offset into twiddle_factors
        int twiddle_idx = tid & (stride - 1); // Twiddle factor index
        float2 w = twiddle_factors[base_offset + twiddle_idx];
        if (mode == 1) w.y = -w.y;

        // Perform the butterfly operation
        int base_idx = (tid << 1) - (twiddle_idx); // base_idx = tid * 2 - (tid % stride);
        int pair_offset = base_idx + stride;
        Butterfly(&d_shared_1[base_idx], &d_shared_1[pair_offset], w);
        // __syncthreads();
    }
    // Transpose
    int out_idx_col = row;
    if (bit_reverse) {
        out_idx_col = (__brev(out_idx_col) >> (32 - LOG2_TILE_WIDTH));
    }
    for (int i = 0; i < (TILE_WIDTH/blockDim.x); i++) {
        int out_idx_row = tid + i * blockDim.x;
        d_shared_2[out_idx_row * (TILE_WIDTH+1) + out_idx_col] = d_shared_1[tid + i * blockDim.x];
    }
    // __syncthreads();
}

__global__ void fft2d_kernel(int mode, int rowLen, int logn, float2* d_out, float2* d_in) {
    __shared__ float2 d_shared_1[TILE_WIDTH * (TILE_WIDTH+1)];
    __shared__ float2 d_shared_2[TILE_WIDTH * (TILE_WIDTH+1)];

    int b = blockIdx.x;

    int row_idx = threadIdx.y;

    for (int i = 0; i < (TILE_WIDTH/blockDim.x); i++) {
        int col_idx = threadIdx.x + i * blockDim.x;
        
        // Load tile into shared memory
        int bit_rev_idx = (__brev(col_idx) >> (32 - LOG2_TILE_WIDTH));
        d_shared_1[row_idx * (TILE_WIDTH+1) + bit_rev_idx] = d_in[b * (rowLen * rowLen) + row_idx * rowLen + col_idx];
    }
    __syncthreads();

    // Do the FFT itself for the row
    InnerFFT_row(mode, row_idx, rowLen, &d_shared_1[row_idx * (TILE_WIDTH+1)], d_shared_2, true);
    __syncthreads();
    
    InnerFFT_row(mode, row_idx, rowLen, &d_shared_2[row_idx * (TILE_WIDTH+1)], d_shared_1, false);
    __syncthreads();

    for (int i = 0; i < (TILE_WIDTH/blockDim.x); i++) {
        int col_idx = threadIdx.x + i * blockDim.x;
        d_in[b * (rowLen * rowLen) + row_idx * rowLen + col_idx] = d_shared_1[row_idx * (TILE_WIDTH+1) + col_idx];
    }
}

inline void fft2d_32x32(int mode, float2* in, int N) {
    dim3 gridDim_fft(N, 1, 1);      
    dim3 blockDim_fft(TILE_WIDTH/2, TILE_WIDTH, 1); 
    fft2d_kernel<<<gridDim_fft, blockDim_fft>>>(mode, TILE_WIDTH, LOG2_TILE_WIDTH, in, in);
}

__device__ inline float divide_by_pow2(float x, int n) { // x / (2^n)
    int bits = __float_as_int(x);          // Interpret float as int
    bits -= (n << 23);                     // Subtract n from the exponent (exponent is in bits 23-30)
    return __int_as_float(bits);           // Convert back to float
}

// 3. FFT Multiplication Kernel
__global__ void multiply_fft_kernel(const float2* input_fft, 
                                    const float2* kernel_fft, 
                                    float2* output_fft, 
                                    int tiles_h, int tiles_w, int B, int M, int C) {
    int tile_h = blockIdx.y;
    int tile_w = blockIdx.x;

    int thread_h = threadIdx.y;
    int thread_w = threadIdx.x;

    int b = blockIdx.z / M;
    int m = blockIdx.z % M;

    // __shared__ float2 s_input_fft[TILE_WIDTH][TILE_WIDTH];
    // __shared__ float2 s_kernel_fft[TILE_WIDTH][TILE_WIDTH];

    // float2 sum = {0.0f, 0.0f};
    // for (int c = 0; c < C; ++c) {
    //     int input_idx = b * (C * tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + c * (tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_h * (tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_w * (TILE_WIDTH * TILE_WIDTH) + thread_h * (TILE_WIDTH) + thread_w;
    //     int kernel_idx = m * (C * TILE_WIDTH * TILE_WIDTH) + c * (TILE_WIDTH * TILE_WIDTH) + thread_h * (TILE_WIDTH) + thread_w;
    //     s_input_fft[threadIdx.y][threadIdx.x] = input_fft[input_idx];
    //     s_kernel_fft[threadIdx.y][threadIdx.x] = kernel_fft[kernel_idx];
    //     __syncthreads();
    //     float2 a = input_fft[input_idx];
    //     float2 b = kernel_fft[kernel_idx];

    //     float2 prod;
    //     prod.x = a.x * b.x - a.y * b.y;
    //     prod.y = a.x * b.y + a.y * b.x;

    //     sum.x += prod.x;
    //     sum.y += prod.y;
    //     __syncthreads();
    // }
    // sum.x /= (float)(TILE_WIDTH * TILE_WIDTH);
    // sum.y /= (float)(TILE_WIDTH * TILE_WIDTH);
    // int output_idx = b * (M * tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + m * (tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_h * (tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_w * (TILE_WIDTH * TILE_WIDTH) + thread_h * (TILE_WIDTH) + thread_w;
    // output_fft[output_idx] = sum;

    float2 sum = {0.0f, 0.0f};
    #pragma unroll
    for (int c = 0; c < C; ++c) {
        int input_idx = b * (C * tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + c * (tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_h * (tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_w * (TILE_WIDTH * TILE_WIDTH) + thread_h * (TILE_WIDTH) + thread_w;
        int kernel_idx = m * (C * TILE_WIDTH * TILE_WIDTH) + c * (TILE_WIDTH * TILE_WIDTH) + thread_h * (TILE_WIDTH) + thread_w;
        float2 a = input_fft[input_idx];
        float2 b = kernel_fft[kernel_idx];

        sum.x += a.x * b.x - a.y * b.y;
        sum.y += a.x * b.y + a.y * b.x;
    }

    // sum.x = divide_by_pow2(sum.x, LOG2_TILE_WIDTH * LOG2_TILE_WIDTH);
    // sum.y = divide_by_pow2(sum.y, LOG2_TILE_WIDTH * LOG2_TILE_WIDTH);

    sum.x /= (float)(TILE_WIDTH * TILE_WIDTH);
    sum.y /= (float)(TILE_WIDTH * TILE_WIDTH);
    int output_idx = b * (M * tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + m * (tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_h * (tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_w * (TILE_WIDTH * TILE_WIDTH) + thread_h * (TILE_WIDTH) + thread_w;
    output_fft[output_idx] = sum;
}

// 4. Inverse FFT Normalization Kernel
__global__ void normalize_ifft_kernel(float2* ifft_output, 
                                      int total_elements, 
                                      float norm_factor) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid >= total_elements) return;

    ifft_output[tid].x /= norm_factor;
    ifft_output[tid].y /= norm_factor;
}

// 5. Extract Valid Output and Save
__global__ void extract_valid_kernel(const float2* ifft_output, 
                                     float* final_output, 
                                     int B, int M, 
                                     int H_out, int W_out, 
                                     int K, 
                                     int tiles_h, int tiles_w, 
                                     int T_in, int T_pad, 
                                     int stride) {
    // Determine output indices from blockIdx and threadIdx
    int tile_h = blockIdx.y;
    int tile_w = blockIdx.x;

    int thread_h = threadIdx.y;
    int thread_w = threadIdx.x;

    int b = blockIdx.z / M;
    int m = blockIdx.z % M;

    // Calculate the position in the output
    int out_h = tile_h * stride + thread_h;
    int out_w = tile_w * stride + thread_w;

    int offset = K - 1;

    if (thread_h < stride && thread_w < stride && out_h < H_out && out_w < W_out) {
        int input_idx = b * (M * tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + m * (tiles_h * tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_h * (tiles_w * TILE_WIDTH * TILE_WIDTH) + tile_w * (TILE_WIDTH * TILE_WIDTH) + (thread_h + offset) * (TILE_WIDTH) + (thread_w + offset);
        int output_idx = b * (M * H_out * W_out) + m * (H_out * W_out) + out_h * W_out + out_w;
        final_output[output_idx] = ifft_output[input_idx].x;
    }
}

// 9. FFT-Based Convolution Function with Pipelining Using Streams
void forward_fft_conv_pipelined(cudaStream_t *streams, float* output, const float* input, const float* kernel, 
                                int B, int M, int C, int H, int W, int K,
                                float2** d_padded_input_stream, float2* d_padded_kernel, 
                                float2** d_output_fft_stream, float* d_flipped_kernel) {
    
    // Define tile parameters
    const int T_in = TILE_WIDTH - (K - 1);    // Input tile size before padding (26)
    const int stride = T_in - (K - 1);        // Stride between tiles (20 for K=7)
    const int T_pad = TILE_WIDTH;             // Padded tile size (32)
    const int tiles_h = (H + stride - 1) / stride; // Number of tiles vertically
    const int tiles_w = (W + stride - 1) / stride; // Number of tiles horizontally

    // Compute output dimensions
    const int H_out = H - K + 1;
    const int W_out = W - K + 1;

    // Precompute and pad kernel_fft (only once, since it's shared)
    // Flip the kernel
    int threads_flip = 256;
    int blocks_flip = (M * C * K * K + threads_flip - 1) / threads_flip;
    flip_kernel_spatial<<<blocks_flip, threads_flip>>>(kernel, d_flipped_kernel, M, C, K);
    CHECK_CUDA(cudaGetLastError());
    CHECK_CUDA(cudaDeviceSynchronize());

    // Pad the flipped kernel
    dim3 blockDim_pad_kernel(TILE_WIDTH, TILE_WIDTH);
    dim3 gridDim_pad_kernel(M, C);
    pad_flipped_kernel<<<gridDim_pad_kernel, blockDim_pad_kernel>>>(d_flipped_kernel, d_padded_kernel, M, C, K, T_pad);
    CHECK_CUDA(cudaGetLastError());
    CHECK_CUDA(cudaDeviceSynchronize());

    // Launch FFT on kernel_fft (already padded and flipped)
    fft2d_32x32(0, d_padded_kernel, M * C);
    CHECK_CUDA(cudaGetLastError());
    CHECK_CUDA(cudaDeviceSynchronize());

    // Start processing mini-batches with pipelining
    for (int mb = 0; mb < NUM_STREAMS; ++mb) {
        int stream_id = mb;
        cudaStream_t stream = streams[stream_id];

        // Determine the start index and current mini-batch size
        int start_b = mb * MINI_B;

        // Launch padding kernel for input mini-batch
        dim3 blockDim_pad(TILE_WIDTH, TILE_WIDTH);
        dim3 gridDim_pad(tiles_w, tiles_h, MINI_B * C);
        pad_input_kernel<<<gridDim_pad, blockDim_pad, 0, stream>>>(
            input + start_b * C * H * W, 
            d_padded_input_stream[stream_id],
            MINI_B, C, H, W, K, stride, T_in, T_pad, tiles_h, tiles_w);
        CHECK_CUDA(cudaGetLastError());

        // Perform FFT on input mini-batch
        fft2d_32x32(0, d_padded_input_stream[stream_id], MINI_B * C * tiles_h * tiles_w);
        CHECK_CUDA(cudaGetLastError());

        // Perform element-wise multiplication and summation
        dim3 blockDim_multiply(TILE_WIDTH, TILE_WIDTH);
        dim3 gridDim_multiply(tiles_w, tiles_h, MINI_B * M);
        multiply_fft_kernel<<<gridDim_multiply, blockDim_multiply, 0, stream>>>(
            d_padded_input_stream[stream_id], 
            d_padded_kernel, 
            d_output_fft_stream[stream_id], 
            tiles_h, tiles_w, MINI_B, M, C);
        CHECK_CUDA(cudaGetLastError());

        // Perform inverse FFT on output mini-batch
        fft2d_32x32(1, d_output_fft_stream[stream_id], MINI_B * M * tiles_h * tiles_w);
        CHECK_CUDA(cudaGetLastError());

        // Extract valid output and write to global memory
        dim3 blockDim_extract(TILE_WIDTH, TILE_WIDTH);
        dim3 gridDim_extract(tiles_w, tiles_h, MINI_B * M);
        extract_valid_kernel<<<gridDim_extract, blockDim_extract, 0, stream>>>(
            d_output_fft_stream[stream_id],
            output + start_b * M * H_out * W_out, 
            MINI_B, M, H_out, W_out, 
            K, tiles_h, tiles_w, T_in, T_pad, stride);
        CHECK_CUDA(cudaGetLastError());
    }

    // Synchronize all streams
    for (int i = 0; i < NUM_STREAMS; ++i) {
        CHECK_CUDA(cudaStreamSynchronize(streams[i]));
    }
}

template <>
void forward<gpu, float>(mshadow::Tensor<gpu, 4, float> &y,
                         const mshadow::Tensor<gpu, 4, float> &x,
                         const mshadow::Tensor<gpu, 4, float> &w)
{
    int device_count = 0;
    CHECK_CUDA(cudaGetDeviceCount(&device_count));
    std::cout << "Number of CUDA devices: " << device_count << "\n";

    for (int i = 0; i < device_count; ++i) {
        cudaDeviceProp prop;
        CHECK_CUDA(cudaGetDeviceProperties(&prop, i));
        std::cout << "Device " << i << ": " << prop.name << "\n";
    }

    // Assuming the V100 is device 0 or device 1, set it:
    CHECK_CUDA(cudaSetDevice(0)); // or 1, whichever corresponds to the V100

    const int B = x.shape_[0];
    const int M = y.shape_[1]; // num_filter
    const int C = x.shape_[1];
    const int H = x.shape_[2];
    const int W = x.shape_[3];
    const int K = w.shape_[3];

    std::cerr << "Batch: " << B << std::endl;
    std::cerr << "M: " << M << std::endl;
    std::cerr << "C: " << C << std::endl;
    std::cerr << "H: " << H << std::endl;
    std::cerr << "W: " << W << std::endl;
    std::cerr << "K: " << K << std::endl;

    // Compute output dimensions
    const int H_out = H - K + 1;
    const int W_out = W - K + 1;

    // Determine batch processing subsets
    int num_batches = (B + B_SUB - 1) / B_SUB;

    // Define tile parameters
    const int T_in = TILE_WIDTH - (K - 1);    // Input tile size before padding (26)
    const int stride = T_in - (K - 1);        // Stride between tiles (20 for K=7)
    const int T_pad = TILE_WIDTH;             // Padded tile size (32)
    const int tiles_h = (H + stride - 1) / stride; // Number of tiles vertically
    const int tiles_w = (W + stride - 1) / stride; // Number of tiles horizontally

    float2 h_twiddle_factors[TILE_WIDTH * LOG2_TILE_WIDTH]; // Host array
    int offset = 0;

    for (int stage = 0; stage < LOG2_TILE_WIDTH; ++stage) {
        int N = 1 << (stage + 1); // N = 2, 4, 8, ..., TILE_WIDTH
        for (int k = 0; k < N / 2; ++k) {
            float angle = -2.0f * PI * k / N; // Negative for forward FFT
            h_twiddle_factors[offset + k].x = cosf(angle);
            h_twiddle_factors[offset + k].y = sinf(angle);
        }
        offset += N / 2;
    }

    // Copy to constant memory
    cudaMemcpyToSymbol(twiddle_factors, h_twiddle_factors, sizeof(float2) * TILE_WIDTH * LOG2_TILE_WIDTH);
    
    // Allocate device memory once
    // float2* d_padded_input;
    // CHECK_CUDA(cudaMalloc(&d_padded_input, B_SUB * C * tiles_h * tiles_w * T_pad * T_pad * sizeof(float2)));

    float* d_flipped_kernel;
    CHECK_CUDA(cudaMalloc(&d_flipped_kernel, M * C * K * K * sizeof(float)));

    float2* d_padded_kernel;
    CHECK_CUDA(cudaMalloc(&d_padded_kernel, M * C * T_pad * T_pad * sizeof(float2)));

    // float2* d_output_fft;
    // CHECK_CUDA(cudaMalloc(&d_output_fft, B_SUB * M * tiles_h * tiles_w * T_pad * T_pad * sizeof(float2)));

    // Create CUDA streams
    cudaStream_t streams[NUM_STREAMS];
    for (int i = 0; i < NUM_STREAMS; ++i) {
        CHECK_CUDA(cudaStreamCreate(&streams[i]));
    }

    // Allocate per-stream device memory for input_fft and output_fft
    float2* d_padded_input_stream[NUM_STREAMS];
    float2* d_output_fft_stream[NUM_STREAMS];
    for (int i = 0; i < NUM_STREAMS; ++i) {
        CHECK_CUDA(cudaMalloc(&d_padded_input_stream[i], MINI_B * C * tiles_h * tiles_w * T_pad * T_pad * sizeof(float2)));
        CHECK_CUDA(cudaMalloc(&d_output_fft_stream[i], MINI_B * M * tiles_h * tiles_w * T_pad * T_pad * sizeof(float2)));
    }

    // Iterate over batch subsets
    for (int b = 0; b < B; b += B_SUB) {
        forward_fft_conv_pipelined(
            streams,
            y.dptr_ + b * M * H_out * W_out,   // Output offset
            x.dptr_ + b * C * H * W,         // Input offset
            w.dptr_,                          // Kernel pointer (constant across batches)
            B_SUB, M, C, H, W, K,
            d_padded_input_stream, d_padded_kernel, 
            d_output_fft_stream, d_flipped_kernel
        );
    }

    // Cleanup: Free device memory
    cudaFree(d_flipped_kernel);
    cudaFree(d_padded_kernel);
    for (int i = 0; i < NUM_STREAMS; ++i) {
        cudaStreamDestroy(streams[i]);
        cudaFree(d_padded_input_stream[i]);
        cudaFree(d_output_fft_stream[i]);
    }
}

/* 
    This tells mxnet how to do an op when it's not a float.
    This is not used in the ECE408 project
*/
template <typename gpu, typename DType>
void forward(mshadow::Tensor<gpu, 4, DType> &y, 
             const mshadow::Tensor<gpu, 4, DType> &x, 
             const mshadow::Tensor<gpu, 4, DType> &w)
{
    assert(0 && "No forward implementation for other datatypes needed for ECE408");
}

}
}

#endif
