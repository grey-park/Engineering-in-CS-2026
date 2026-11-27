#pragma once
#include <stdint.h>

#define TOPIC_PENDING "tapserve/pending"
#define TOPIC_CLAIM   "tapserve/claim"

enum : uint8_t { KIND_APPEL = 0, KIND_ADDITION = 1, KIND_ENCORE = 2 };
