/* Write-heavy SE-mode workload for gem5 writeback traces.
 *
 * Allocates a few pages, fills them, then rewrites them with different
 * values so dirty lines leave the LLC and become memory writebacks.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    NUM_LINES = 512, /* 512 * 64 = 32 KiB, larger than the default L1D */
    LINE_BYTES = 64
};

static uint8_t buf[NUM_LINES * LINE_BYTES] __attribute__((aligned(64)));

static void fill(uint8_t stamp) {
    for (int i = 0; i < NUM_LINES * LINE_BYTES; i++) {
        buf[i] = (uint8_t)(stamp + (i & 0xff));
    }
}

int main(void) {
    /* Touch every line, then rewrite twice to force writebacks. */
    fill(1);
    fill(2);
    fill(3);

    /* Prevent the compiler from deleting the stores. */
    volatile uint8_t sink = buf[0];
    (void)sink;

    printf("write_array: wrote %d lines of %d bytes\n", NUM_LINES, LINE_BYTES);
    return 0;
}
