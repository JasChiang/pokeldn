/* PaperS3 ET047TC1, using the pin map and waveforms in pinned M5GFX.
   No OLED probing, board autodetection, touch, NVS, LED or power-button task. */
#include "display.h"
#include "papers3_model.h"
#include <M5GFX.h>
#include <lgfx/v1/platforms/esp32/Panel_EPD.hpp>
#include <atomic>
#include <cstring>
#include <new>
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

namespace {
constexpr uint32_t REFRESH_MS = 2000;
constexpr uint32_t COUNTERS_MS = 15000;
constexpr uint16_t BLACK = 0x0000, WHITE = 0xffff;

class PaperDisplay : public lgfx::LGFX_Device {
    lgfx::Bus_EPD bus;
    lgfx::Panel_EPD panel;
public:
    PaperDisplay() {
        auto b = bus.config();
        b.bus_speed = 16000000;
        const int8_t data[8] = {6, 14, 7, 12, 9, 11, 8, 10};
        std::memcpy(b.pin_data, data, sizeof(data));
        b.pin_pwr = 46; b.pin_spv = 17; b.pin_ckv = 18; b.pin_sph = 13;
        b.pin_oe = 45; b.pin_le = 15; b.pin_cl = 16; b.bus_width = 8;
        bus.config(b);
        panel.setBus(&bus);
        auto detail = panel.config_detail();
        detail.line_padding = 8;
        detail.task_priority = 1;
        detail.task_pinned_core = 0;
        panel.config_detail(detail);
        auto p = panel.config();
        p.memory_width = p.panel_width = 960;
        p.memory_height = p.panel_height = 540;
        p.offset_rotation = 3; p.offset_x = p.offset_y = 0;
        p.bus_shared = false;
        panel.config(p);
        setPanel(&panel);
    }
};

struct Message {
    uint32_t generation;
    uint16_t length;
    uint8_t payload[PAPER_COMMAND_MAX];
};
QueueHandle_t commands;
display_state_t get_state;
std::atomic<bool> ready{false};
std::atomic<uint32_t> generation{0}, updates{0};
enum InitState { STARTING, READY, NO_PSRAM, INIT_FAILED, NO_TASK };
std::atomic<InitState> init_state{STARTING};

const char *radio_label(const scene_radio_t &r) {
    switch (r.mode) {
    case SCENE_JOINING: return "Joining console";
    case SCENE_JOINED: return "Linked to console";
    case SCENE_HOSTING: return r.stations ? "Console connected" : "Waiting for console";
    case SCENE_SNIFFING: return "Scanning radio";
    default: return "Radio ready";
    }
}
const char *show_label(const paper_model_t &m, const scene_radio_t &r) {
    switch (m.show) {
    case SHOW_TRADE: return "Offering Pokemon";
    case SHOW_TRADED: return m.arrived ? "Received Pokemon" : "Incoming Pokemon";
    case SHOW_GIFT: return "Offering gift";
    case SHOW_GIFTED: return "Gift sent";
    default: return r.mode == SCENE_IDLE ? "USB Serial/JTAG" : "No Pokemon preview";
    }
}

const char *content_title(const paper_model_t &m, const scene_radio_t &r) {
    if (m.title[0]) return m.title;
    if (m.show != SHOW_AUTO) return show_label(m, r);
    switch (r.mode) {
    case SCENE_HOSTING: return "Room active";
    case SCENE_JOINING: return "Connecting";
    case SCENE_JOINED: return "Connected";
    case SCENE_SNIFFING: return "Scanning";
    default: return "Idle";
    }
}
const char *content_line(const paper_model_t &m, const scene_radio_t &r) {
    if (m.line[0]) return m.line;
    if (m.show != SHOW_AUTO) return "No name provided by App";
    return r.mode == SCENE_IDLE ? "Start a session in the Mac app" :
                                "Waiting for App display data";
}

unsigned sprite_slot(const paper_model_t &m) {
    return m.show == SHOW_TRADED ? SLOT_THEIRS :
           (m.show == SHOW_GIFT || m.show == SHOW_GIFTED ? SLOT_GIFT : SLOT_OURS);
}
bool has_sprite(const paper_model_t &m) {
    const paper_sprite_t &s = m.sprite[sprite_slot(m)];
    return m.show != SHOW_AUTO && s.width && s.height;
}

void ball(PaperDisplay &d, int cx, int cy) {
    d.drawCircle(cx, cy, 62, BLACK);
    d.drawCircle(cx, cy, 60, BLACK);
    d.drawLine(cx - 60, cy, cx + 60, cy, BLACK);
    d.fillCircle(cx, cy, 18, WHITE);
    d.drawCircle(cx, cy, 18, BLACK);
    d.drawCircle(cx, cy, 10, BLACK);
}
void sprite(PaperDisplay &d, const paper_model_t &m) {
    const paper_sprite_t &s = m.sprite[sprite_slot(m)];
    if (!has_sprite(m)) { ball(d, 762, 266); return; }
    constexpr int scale = 4;
    const int x0 = 762 - s.width * scale / 2, y0 = 266 - s.height * scale / 2;
    // Host sprites light the body on a black OLED background. Keep that contrast.
    d.fillRoundRect(618, 122, 288, 288, 12, BLACK);
    for (int y = 0; y < s.height; ++y)
        for (int x = 0; x < s.width; ++x)
            if (s.bits[y * ((s.width + 7) / 8) + x / 8] & (0x80 >> (x & 7)))
                d.fillRect(x0 + x * scale, y0 + y * scale, scale, scale, WHITE);
}

void draw(PaperDisplay &d, const paper_model_t &m, const scene_radio_t &r, bool first) {
    d.setEpdMode(first ? lgfx::epd_mode_t::epd_quality : lgfx::epd_mode_t::epd_fast);
    d.startWrite();
    d.fillScreen(WHITE);
    d.setTextColor(BLACK, WHITE);
    d.setFont(&fonts::Font4);
    d.setTextSize(2);
    d.setCursor(34, 22); d.print("PokeLDN");
    d.setFont(&fonts::Font2); d.setTextSize(1);
    d.setCursor(625, 35); d.print("PaperS3 / Wireless 1.6.2 / v2");
    d.drawFastHLine(34, 85, 892, BLACK);
    d.setFont(&fonts::Font4); d.setTextSize(1.5);
    d.setCursor(34, 119); d.print(radio_label(r));
    d.setTextSize(1);
    d.setCursor(34, 188); d.print(show_label(m, r));
    d.setTextSize(2);
    d.setCursor(34, 242); d.print(content_title(m, r));
    d.setTextSize(1);
    d.setCursor(34, 313); d.print(content_line(m, r));
    d.setFont(&fonts::Font2);
    d.setCursor(34, 379); d.printf("Consoles: %u   RX: %lu   TX: %lu", r.stations,
                                 (unsigned long)r.rx, (unsigned long)r.tx);
    sprite(d, m);
    if (!has_sprite(m)) {
        d.setCursor(638, 413);
        d.print(m.show == SHOW_AUTO ? (r.mode == SCENE_IDLE ? "No active preview" :
                                      "Preview not received") : "Image unavailable");
    }
    d.drawFastHLine(34, 440, 892, BLACK);
    d.setCursor(34, 462); d.print("Use the Mac app for the link code and session controls.");
    d.setCursor(34, 490); d.print("E-paper keeps its last image when powered off. Check the app for live status.");
    d.endWrite();
    d.display();
    d.waitDisplay();
}

void display_task(void *) {
    if (!esp_psram_is_initialized() || heap_caps_get_free_size(MALLOC_CAP_SPIRAM) < 2 * 1024 * 1024) {
        // The radio remains usable. Never turn an optional display failure into a reboot.
        init_state.store(NO_PSRAM);
        vTaskDelete(nullptr);
        return;
    }
    auto *d = new (std::nothrow) PaperDisplay;
    if (!d) { init_state.store(INIT_FAILED); vTaskDelete(nullptr); return; }
    if (!d->init()) { init_state.store(INIT_FAILED); vTaskDelete(nullptr); return; }
    d->setRotation(1); // offset_rotation=3: native 960x540 landscape
    d->setAutoDisplay(false);
    ready.store(true);
    init_state.store(READY);
    paper_model_t model{}, painted{};
    scene_radio_t last{}, previous{};
    bool first = true, active = false;
    uint32_t refreshed = 0, counters = 0;
    uint32_t seen_generation = generation.load();
    for (;;) {
        const uint32_t epoch = generation.load();
        if (seen_generation != epoch) {
            paper_model_reset(&model);
            seen_generation = epoch;
        }
        Message msg;
        while (xQueueReceive(commands, &msg, 0) == pdTRUE) {
            if (msg.generation != generation.load()) continue;
            if (seen_generation != msg.generation) {
                paper_model_reset(&model); seen_generation = msg.generation;
            }
            paper_model_command(&model, msg.payload, msg.length);
        }
        scene_radio_t state{};
        if (get_state) get_state(&state);
        if (state.mode != SCENE_IDLE) active = true;
        if (active && state.mode == SCENE_IDLE && previous.mode != SCENE_IDLE) {
            paper_model_reset(&model);
            active = false;
        }
        previous = state;
        const uint32_t now = static_cast<uint32_t>(esp_timer_get_time() / 1000);
        bool changed = first || model.show != painted.show || model.arrived != painted.arrived ||
                       std::strcmp(model.title, painted.title) || std::strcmp(model.line, painted.line) ||
                       std::memcmp(model.sprite, painted.sprite, sizeof(model.sprite)) ||
                       state.mode != last.mode || state.stations != last.stations;
        if (state.mode != SCENE_IDLE && now - counters >= COUNTERS_MS &&
            (state.rx != last.rx || state.tx != last.tx)) changed = true;
        if (changed && (first || now - refreshed >= REFRESH_MS)) {
            // A quality pass occasionally clears residual fast-refresh ghosting.
            draw(*d, model, state, first || updates.load() % 12 == 0);
            updates.fetch_add(1);
            painted = model; last = state;
            refreshed = static_cast<uint32_t>(esp_timer_get_time() / 1000);
            counters = refreshed;
            first = false;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
} // namespace

extern "C" bool display_start(display_state_t state) {
    if (commands) return ready.load();
    commands = xQueueCreate(8, sizeof(Message));
    if (!commands) { init_state.store(NO_TASK); return false; }
    get_state = state;
    if (xTaskCreatePinnedToCore(display_task, "papers3-epaper", 8192, nullptr, 1, nullptr, 0) != pdPASS) {
        vQueueDelete(commands); commands = nullptr;
        init_state.store(NO_TASK);
        return false;
    }
    return true; // accepted asynchronous initialization; availability reported by DISPLAY
}
extern "C" bool display_command(const uint8_t *payload, size_t length) {
    const InitState init = init_state.load();
    // A host may offer its Pokemon before EPD initialization finishes. Keep the
    // early commands in the bounded queue rather than silently losing that offer.
    if (!commands || (init != STARTING && init != READY) || !paper_command_valid(payload, length)) return false;
    Message msg{};
    msg.generation = generation.load();
    msg.length = static_cast<uint16_t>(length);
    std::memcpy(msg.payload, payload, length);
    return xQueueSend(commands, &msg, 0) == pdTRUE;
}
extern "C" void display_reset(void) {
    // A full queue must not lose HELLO's reset, and older sprites must never leak
    // into the next host session. Only the display worker touches the model.
    generation.fetch_add(1);
}
extern "C" const char *papers3_display_state(void) {
    static const char *names[] = {"starting", "ready", "no_psram", "init_failed", "no_task"};
    return names[init_state.load()];
}
extern "C" uint32_t papers3_display_updates(void) { return updates.load(); }
