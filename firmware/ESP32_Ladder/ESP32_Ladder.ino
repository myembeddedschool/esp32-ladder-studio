#include "plc_core.h"

// Classic ESP32-WROOM-32 development board; change only after checking your PCB.
const uint8_t INPUT_PINS[4] = {25, 26, 27, 32};
const uint8_t OUTPUT_PINS[4] = {2, 19, 21, 22};
const uint32_t SCAN_MS = 10;
Program active = {}, staging = {};
Bits bits = {};
bool running = false, uploading = false, uploadError = false;
char line[512]; size_t lineLength = 0;
bool lineOverflow = false;
uint32_t lastScan = 0, scans = 0;

void applyOutputs() {
  for (uint8_t i = 0; i < 4; ++i) digitalWrite(OUTPUT_PINS[i], bits.outputs[i] ? HIGH : LOW);
}
void stopPLC() { running = false; clearState(bits); applyOutputs(); }
uint8_t mask(const bool* values, uint8_t size) {
  uint8_t m = 0;
  for (uint8_t i = 0; i < size; ++i) if (values[i]) m |= 1U << i;
  return m;
}
void command(const char* cmd) {
  if (!strcmp(cmd, "PING")) Serial.println("PONG ESP32_LADDER_V2");
  else if (!strcmp(cmd, "STOP")) { stopPLC(); Serial.println("OK STOP"); }
  else if (!strcmp(cmd, "BEGIN")) {
    stopPLC(); staging = {}; uploading = true; uploadError = false;
    Serial.println("OK BEGIN");
  } else if (!strncmp(cmd, "R ", 2) || !strncmp(cmd, "T ", 2)) {
    const bool timer = cmd[0] == 'T';
    if (!uploading || !addRung(staging, cmd + 2, timer)) {
      if (uploading) uploadError = true;
      Serial.println("ERR RUNG");
    } else Serial.println(timer ? "OK T" : "OK R");
  } else if (!strcmp(cmd, "COMMIT")) {
    if (!uploading || uploadError || !staging.count) Serial.println("ERR COMMIT");
    else {
      active = staging; uploading = false; clearState(bits);
      Serial.println("OK COMMIT");
    }
  } else if (!strcmp(cmd, "RUN")) {
    if (uploading || !active.count) Serial.println("ERR RUN");
    else { running = true; Serial.println("OK RUN"); }
  } else if (!strcmp(cmd, "STATE")) {
    Serial.print("STATE "); Serial.print(running ? 1 : 0); Serial.print(' ');
    Serial.print(mask(bits.inputs, 4)); Serial.print(' ');
    Serial.print(mask(bits.outputs, 4)); Serial.print(' ');
    Serial.print(mask(bits.memory, 8)); Serial.print(' '); Serial.print(scans);
    Serial.print(' '); Serial.print(mask(bits.timers, 4));
    for (uint8_t i = 0; i < 4; ++i) { Serial.print(' '); Serial.print(bits.elapsed[i]); }
    Serial.println("");
  } else Serial.println("ERR COMMAND");
}
void setup() {
  for (uint8_t i = 0; i < 4; ++i) {
    pinMode(INPUT_PINS[i], INPUT_PULLUP);
    pinMode(OUTPUT_PINS[i], OUTPUT); digitalWrite(OUTPUT_PINS[i], LOW);
  }
  Serial.begin(115200);
}
void loop() {
  const uint32_t now = millis();
  if ((uint32_t)(now - lastScan) >= SCAN_MS) {
    lastScan = now;
    for (uint8_t i = 0; i < 4; ++i) bits.inputs[i] = digitalRead(INPUT_PINS[i]) == LOW;
    if (running) scanProgram(active, bits, now);
    applyOutputs(); ++scans;
  }
  // Limit serial work per loop, so a continuous upload stream cannot starve scans.
  for (uint16_t n = 0; n < 128 && Serial.available(); ++n) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (lineOverflow) {
        if (uploading) uploadError = true;
        Serial.println("ERR LINE_TOO_LONG");
      } else { line[lineLength] = 0; command(line); }
      lineLength = 0; lineOverflow = false;
    } else if (!lineOverflow) {
      if (lineLength < sizeof(line) - 1) line[lineLength++] = c;
      else lineOverflow = true;
    }
  }
}
