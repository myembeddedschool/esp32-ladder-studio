#pragma once
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

// Deliberately small teaching runtime: parallel branches of series contacts.
struct Contact { uint8_t area, index; bool inverted; };
struct Branch { Contact contacts[8]; uint8_t count; };
struct Rung { Branch branches[4]; uint8_t count, area, index, kind; uint32_t preset; };
struct Program { Rung rungs[16]; uint8_t count; };
struct Bits {
  bool inputs[4], outputs[4], memory[8], timers[4], timing[4];
  uint32_t started[4], elapsed[4];
};

inline bool parseTag(const char* s, uint8_t &area, uint8_t &index) {
  if (!s || strlen(s) != 2 || s[1] < '0' || s[1] > '7') return false;
  area = s[0] == 'I' ? 0 : s[0] == 'Q' ? 1 : s[0] == 'M' ? 2 : s[0] == 'T' ? 3 : 255;
  index = s[1] - '0';
  return area < 4 && (area == 2 || index < 4);
}
inline bool readBit(const Bits &b, uint8_t area, uint8_t i) {
  return area == 0 ? b.inputs[i] : area == 1 ? b.outputs[i] : area == 2 ? b.memory[i] : b.timers[i];
}
inline bool rungValue(const Rung &r, const Bits &b) {
  bool value = false;
  for (uint8_t j = 0; j < r.count; ++j) {
    bool branch = true;
    for (uint8_t k = 0; k < r.branches[j].count; ++k) {
      const Contact &c = r.branches[j].contacts[k];
      branch = branch && (readBit(b, c.area, c.index) != c.inverted);
    }
    value = value || branch;
  }
  return value;
}
inline void scanProgram(const Program &p, Bits &b, uint32_t nowMs = 0) {
  // Rungs execute top to bottom. Writes are visible to later rungs immediately.
  for (uint8_t i = 0; i < p.count; ++i) {
    const Rung &r = p.rungs[i];
    bool value = rungValue(r, b);
    if (r.kind == 1) {
      const uint8_t t = r.index;
      if (!value) {
        b.timers[t] = false; b.timing[t] = false; b.elapsed[t] = 0;
      } else {
        if (!b.timing[t]) { b.timing[t] = true; b.started[t] = nowMs; }
        const uint32_t elapsed = nowMs - b.started[t];
        // Once done, remain done until disabled (even after millis() wrap).
        b.timers[t] = b.timers[t] || elapsed >= r.preset;
        b.elapsed[t] = b.timers[t] ? r.preset : elapsed;
      }
    } else if (r.area == 1) b.outputs[r.index] = value;
    else b.memory[r.index] = value;
  }
}
inline void clearState(Bits &b) {
  memset(b.outputs, 0, sizeof(b.outputs));
  memset(b.memory, 0, sizeof(b.memory));
  memset(b.timers, 0, sizeof(b.timers));
  memset(b.timing, 0, sizeof(b.timing));
  memset(b.elapsed, 0, sizeof(b.elapsed));
}
inline bool parseRung(const char* source, Rung &result) {
  // Format: Q0 I0,!I1;Q0,!I1
  if (!source || strlen(source) >= 512) return false;
  char buf[512]; strcpy(buf, source);
  char* split = strchr(buf, ' ');
  if (!split) return false;
  *split++ = '\0';
  Rung temp = {};
  if (!parseTag(buf, temp.area, temp.index) || temp.area == 0 || temp.area == 3 || !*split) return false;
  // Reject empty tokens: strtok would otherwise silently accept them.
  if (*split == ';' || *split == ',' || split[strlen(split)-1] == ';' || split[strlen(split)-1] == ',' ||
      strstr(split, ";;") || strstr(split, ",,") || strstr(split, ",;") || strstr(split, ";,")) return false;
  char *branchSave = nullptr;
  for (char* branch = strtok_r(split, ";", &branchSave); branch;
       branch = strtok_r(nullptr, ";", &branchSave)) {
    if (temp.count >= 4) return false;
    Branch &br = temp.branches[temp.count++];
    char *contactSave = nullptr;
    for (char* token = strtok_r(branch, ",", &contactSave); token;
         token = strtok_r(nullptr, ",", &contactSave)) {
      if (br.count >= 8) return false;
      Contact &c = br.contacts[br.count++];
      c.inverted = token[0] == '!';
      if (!parseTag(token + (c.inverted ? 1 : 0), c.area, c.index)) return false;
    }
    if (!br.count) return false;
  }
  if (!temp.count) return false;
  result = temp;
  return true;
}
inline bool parseTimer(const char* source, Rung &result) {
  // Format: T0 1000 !T1
  if (!source || strlen(source) >= 500) return false;
  char buf[512]; strcpy(buf, source);
  char* preset = strchr(buf, ' ');
  if (!preset) return false;
  *preset++ = 0;
  uint8_t area, index;
  if (!parseTag(buf, area, index) || area != 3) return false;
  char* conditions = strchr(preset, ' ');
  if (!conditions) return false;
  *conditions++ = 0;
  if (!*preset || !*conditions) return false;
  for (const char* c = preset; *c; ++c) if (*c < '0' || *c > '9') return false;
  if (strlen(preset) > 7) return false;
  const unsigned long duration = strtoul(preset, nullptr, 10);
  if (duration < 1 || duration > 3600000) return false;
  char ordinary[512]; snprintf(ordinary, sizeof(ordinary), "M0 %s", conditions);
  Rung temp = {};
  if (!parseRung(ordinary, temp)) return false;
  temp.area = 3; temp.index = index; temp.kind = 1; temp.preset = (uint32_t)duration;
  result = temp; return true;
}
inline bool addRung(Program &p, const char* source, bool timer = false) {
  if (p.count >= 16) return false;
  Rung rung = {};
  if (!(timer ? parseTimer(source, rung) : parseRung(source, rung))) return false;
  // A tag has one writer. This also prevents misleading online highlighting.
  for (uint8_t i = 0; i < p.count; ++i)
    if (p.rungs[i].area == rung.area && p.rungs[i].index == rung.index) return false;
  p.rungs[p.count++] = rung;
  return true;
}
