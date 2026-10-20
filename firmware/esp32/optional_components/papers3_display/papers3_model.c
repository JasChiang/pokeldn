#include "papers3_model.h"
#include "scene.h"
#include <string.h>

bool paper_command_valid(const uint8_t *p, size_t n)
{
    if (!p || n < 4 || n > PAPER_COMMAND_MAX) return false;
    if (p[0] == DISPLAY_OP_SPRITE)
        return p[1] < SLOTS && p[2] <= SPRITE_W && p[3] <= SPRITE_H &&
               n == 4 + (size_t)((p[2] + 7) / 8) * p[3];
    return p[0] == DISPLAY_OP_SHOW && p[1] < SHOWS;
}

void paper_model_reset(paper_model_t *model) { memset(model, 0, sizeof(*model)); }

static void copy_text(char dst[PAPER_TEXT], const uint8_t **p, const uint8_t *end)
{
    size_t n = 0;
    while (*p < end && **p) {
        uint8_t ch = *(*p)++;
        if (n < PAPER_TEXT - 1) dst[n++] = ch >= 32 && ch <= 126 ? ch : '?';
    }
    dst[n] = 0;
    if (*p < end) ++*p;
}

bool paper_model_command(paper_model_t *model, const uint8_t *p, size_t n)
{
    if (!paper_command_valid(p, n)) return false;
    if (p[0] == DISPLAY_OP_SPRITE) {
        paper_sprite_t *sprite = &model->sprite[p[1]];
        memset(sprite, 0, sizeof(*sprite));
        sprite->width = p[2]; sprite->height = p[3];
        memcpy(sprite->bits, p + 4, n - 4);
    } else if (p[1] == SHOW_ARRIVED) {
        if (model->show == SHOW_TRADED) model->arrived = true;
    } else {
        model->show = p[1];
        model->arrived = false;
        const uint8_t *text = p + 4, *end = p + n;
        copy_text(model->title, &text, end);
        copy_text(model->line, &text, end);
    }
    return true;
}
