/* Stable electronic-paper view of the existing DISPLAY protocol. No hardware. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
#define PAPER_TEXT 22
#define PAPER_SPRITE_BYTES 512
#define PAPER_COMMAND_MAX (4 + PAPER_SPRITE_BYTES)
typedef struct {
    uint8_t width, height;
    uint8_t bits[PAPER_SPRITE_BYTES];
} paper_sprite_t;
typedef struct {
    uint8_t show;
    bool arrived;
    char title[PAPER_TEXT], line[PAPER_TEXT];
    paper_sprite_t sprite[3];
} paper_model_t;

bool paper_command_valid(const uint8_t *p, size_t n);
void paper_model_reset(paper_model_t *model);
/* Invalid commands leave the model intact. hold_s is intentionally not used:
   an e-paper snapshot stays until the next explicit host/radio state change. */
bool paper_model_command(paper_model_t *model, const uint8_t *p, size_t n);
#ifdef __cplusplus
}
#endif
