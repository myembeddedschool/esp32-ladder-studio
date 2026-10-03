// Native test of the actual firmware and parser, using Arduino I/O stand-ins.
#include <assert.h>
#include <string>
#include <iostream>
#include <stdint.h>
const int HIGH = 1, LOW = 0, INPUT_PULLUP = 2, OUTPUT = 3;
int pins[40] = {};
uint32_t nowMs = 0;
void pinMode(int, int) {}
void digitalWrite(int pin, int value) { pins[pin] = value; }
int digitalRead(int pin) { return pins[pin]; }
uint32_t millis() { return nowMs; }
struct FakeSerial {
  std::string tx, rx;
  void begin(int) {}
  int available() { return (int)rx.size(); }
  char read() { char c = rx[0]; rx.erase(0, 1); return c; }
  void print(const char* x) { tx += x; }
  void print(char x) { tx += x; }
  template<class T> void print(T x) { tx += std::to_string(x); }
  template<class T> void println(T x) { print(x); tx += "\n"; }
} Serial;
#include "../firmware/ESP32_Ladder/ESP32_Ladder.ino"

void expect(const char* cmd, const char* reply) {
  Serial.tx.clear(); command(cmd); assert(Serial.tx == std::string(reply) + "\n");
}
void advance() { nowMs += 10; loop(); }
int main() {
  setup();
  for (uint8_t pin : INPUT_PINS) pins[pin] = HIGH;
  assert(!running);
  expect("RUN", "ERR RUN");
  expect("PING", "PONG ESP32_LADDER_V2");
  expect("BEGIN", "OK BEGIN");
  expect("R Q0 I0,!I1;Q0,!I1", "OK R");
  expect("R Q1 Q0,I2", "OK R");
  expect("COMMIT", "OK COMMIT");
  expect("RUN", "OK RUN");
  pins[25] = LOW; advance(); assert(pins[18] == HIGH);
  pins[25] = HIGH; advance(); assert(pins[18] == HIGH);
  pins[27] = LOW; advance(); assert(pins[19] == HIGH);
  pins[26] = LOW; advance(); assert(pins[18] == LOW && pins[19] == LOW);
  expect("STOP", "OK STOP");
  expect("BEGIN", "OK BEGIN");
  expect("R Q0 I0", "OK R");
  expect("R Q0 I1", "ERR RUNG");
  expect("COMMIT", "ERR COMMIT");
  assert(active.count == 2 && !running); // Failed upload does not replace active.
  expect("BEGIN", "OK BEGIN");
  expect("R M0 I0", "OK R");
  expect("R Q0 M0", "OK R");
  expect("COMMIT", "OK COMMIT");
  expect("RUN", "OK RUN");
  pins[25] = LOW; advance(); assert(bits.memory[0] && pins[18] == HIGH);
  expect("STOP", "OK STOP"); assert(!bits.memory[0] && pins[18] == LOW);
  for (const char* bad : {"I0 I0", "Q4 I0", "Q0 I4", "Q0 ", "Q0 I0,", "Q0 I0;;I1",
                          "Q0 I0;I1;I2;I3;M0", "Q0 I0,I0,I0,I0,I0,I0,I0,I0,I0"}) {
    Rung rung = {}; assert(!parseRung(bad, rung));
  }
  // Actual serial line assembly, including oversized lines.
  expect("BEGIN", "OK BEGIN");
  Serial.tx.clear(); Serial.rx = std::string(520, 'X') + "\n";
  while (Serial.available()) advance();
  assert(Serial.tx.find("ERR LINE_TOO_LONG") != std::string::npos);
  expect("COMMIT", "ERR COMMIT");
  // Timer interpreter: exact boundaries, reset, 32-bit clock wrap and sustained blink.
  Program blink = {}; Bits blinkBits = {};
  assert(addRung(blink, "T0 1000 !T1", true));
  assert(addRung(blink, "T1 1000 T0", true));
  assert(addRung(blink, "Q0 T0,!T1"));
  unsigned transitions = 0;
  const uint32_t expectedTimes[4] = {1000, 2000, 3020, 4020};
  bool previous = false;
  for (uint32_t ms = 0; ms <= 5000; ms += 10) {
    scanProgram(blink, blinkBits, ms);
    if (blinkBits.outputs[0] != previous) {
      assert(transitions < 4 && ms == expectedTimes[transitions]);
      previous = blinkBits.outputs[0]; ++transitions;
    }
  }
  assert(transitions == 4);
  clearState(blinkBits); assert(!blinkBits.timers[0] && !blinkBits.outputs[0]);
  Program timerTest = {}; Bits timerBits = {}; timerBits.inputs[0] = true;
  assert(addRung(timerTest, "T0 32 I0", true));
  scanProgram(timerTest, timerBits, 0xfffffff0U);
  scanProgram(timerTest, timerBits, 0x0fU); assert(!timerBits.timers[0]);
  scanProgram(timerTest, timerBits, 0x10U); assert(timerBits.timers[0]);
  timerBits.inputs[0] = false; scanProgram(timerTest, timerBits, 0x11U);
  assert(!timerBits.timers[0] && timerBits.elapsed[0] == 0);
  for (const char* bad : {"T4 1000 I0", "T0 0 I0", "T0 -1 I0", "T0 3600001 I0", "Q0 1000 I0", "T0 1.5 I0"}) {
    Rung rung = {}; assert(!parseTimer(bad, rung));
  }
  expect("BEGIN", "OK BEGIN");
  expect("T T0 1000 !T1", "OK T");
  expect("T T1 1000 T0", "OK T");
  expect("R Q0 T0,!T1", "OK R");
  expect("COMMIT", "OK COMMIT");
  expect("RUN", "OK RUN");
  advance();
  Serial.tx.clear(); command("STATE");
  assert(Serial.tx.find("STATE 1 ") == 0);
  expect("STOP", "OK STOP");
  std::cout << "Firmware GPIO, upload, TON timing, clock wrap and blink checks passed\n";
}
