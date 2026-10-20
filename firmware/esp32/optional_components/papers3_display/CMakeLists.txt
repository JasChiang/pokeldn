idf_component_register(
    SRCS "display_papers3.cpp" "papers3_model.c"
    INCLUDE_DIRS "." "../../main"
    PRIV_REQUIRES m5gfx esp_psram esp_timer esp_driver_gpio)
target_compile_features(${COMPONENT_LIB} PRIVATE cxx_std_17)
