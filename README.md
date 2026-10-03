# ESP32 Ladder Studio — starter version 0.3

A small desktop ladder editor and matching ESP32 runtime, built as a starting point for your own PLC programming software. You do not need an embedded Linux board: the PC runs the editor, and the ESP32 runs the ladder scan.

## Included features

- Graphical ladder display and contact selection using dropdowns.
- Normally open (NO) and normally closed (NC) logical contacts.
- Series contacts (AND), parallel branches (OR), Q output coils and M internal bits.
- A parallel group around a selected contact, with shared contacts before and after it.
- Insert a series contact after a selected contact in the editing dialog.
- Offline simulation with clickable input switches and live highlighting.
- Save/open JSON projects, USB upload, RUN/STOP and online tag monitoring.
- A Start/Stop holding circuit and a sensor-gated second output.
- Four non-retentive TON timers, live elapsed-time display and a ready-made LED blink example.

This is a teaching prototype with a small ladder subset. It is not an IEC 61131-3 certified implementation or an industrial PLC replacement. Counters, TOF/TP timers, arithmetic, analogue values, Modbus, Wi-Fi upload, drag-and-drop editing and a packaged Windows EXE are not included yet.

## 1. Try the editor without hardware

Install Python 3 on Windows with Tkinter (included by the usual python.org installer). Extract the ZIP. Open a terminal in the extracted folder:

```bat
py app.py
```

You can also double-click `Start_Windows.bat`. Simulation requires only Python's standard library.

**RUN and STOP are near the top-left, immediately below the title.** Press **F5** for RUN or **Esc** for STOP. Version 0.1.1 moves these controls above the expanding ladder area and sizes the initial window to the screen, fixing bottom controls being clipped on smaller displays. Keyboard shortcuts are disabled while an editing dialog is open.

The Start/Stop example is loaded automatically:

1. Press **RUN**.
2. Check **I0 START**. Q0 turns on.
3. Uncheck I0. Q0 stays on because the parallel Q0 contact holds it.
4. Check **I2 SENSOR**. Q1 turns on while Q0 is on.
5. Check **I1 STOP**. Q0 and Q1 turn off.
6. Uncheck STOP. Outputs stay off until START is pressed again.

Select a branch and press **Edit contacts**, or double-click the branch. The dialog lets you add/remove contacts with a tag dropdown and an NC checkbox. Use **Add parallel branch** for OR logic, **Add rung** for another output, and **Set coil** for a Q or M tag. Save your project before closing.

## Branch around only START, as in a DOL starter diagram

Click **DOL example** for the supplied layout: shared NC I2 overload and NC I1 STOP, followed by a parallel group containing NO I0 START and NO Q0 holding contact. Q0 is the output coil. A second rung copies Q0 to Q1, matching a second output controlled by the contactor state.

To create this yourself:

1. Click **New** and keep coil Q0.
2. In **Edit contacts**, create this series list: NC I2, NC I1, NO I0. Apply.
3. Click the **I0 contact symbol** in the ladder; its selection outline turns yellow.
4. Click **Branch around contact**, enter `Q0`, then accept.
5. The new Q0 holding contact is in parallel with I0 only. STOP and overload remain common to both paths.
6. RUN and test START, release START, STOP, then restart and test overload. With START released, clearing STOP/overload leaves the output off until another start command. A held START can re-energize after STOP/overload clears in this simple level-driven example.

For the other common drawing style, create NO I0 followed by NC I1, then branch around I0 with Q0. I1 remains AFTER the two parallel contacts. Use **Common before** and **Common after** to edit those shared contacts; those groups may be empty. **Add parallel branch** adds another path inside the existing parallel group, not around the shared contacts.

To insert a series contact between two contacts, open **Edit contacts**, select the preceding contact in the list, choose a tag and NO/NC, then click **Insert after / add**. Without a selection it appends at the end.

This version supports **one parallel group per rung**. It does not support arbitrary nested branches or several independent parallel groups on the same rung. Shared-contact projects use file version 2; timer projects use version 3. The updated editor opens old version 1 and 2 projects. Old editors reject newer file versions rather than silently misreading them. Shared contacts expand into equivalent Boolean paths with the same contact and branch limits. **Version 0.3 needs the updated ESP32 firmware, even if you previously flashed version 0.1 or 0.2.** The connection handshake rejects a mismatched firmware version.

## Blink an LED with TON timers

Click **Blink LED**, then **RUN**. No input switch is needed. Q0 begins OFF, turns ON after roughly one second, stays ON for roughly one second, then repeats. STOP immediately clears outputs and timers. To change the speed, select a T0 or T1 rung and click **Set output / timer** to edit its preset in milliseconds.

| Rung | Condition | Instruction | Purpose |
|---|---|---|---|
| 1 | NC T1 | TON T0, 1000 ms | Wait through the OFF phase |
| 2 | NO T0 | TON T1, 1000 ms | Time the ON phase |
| 3 | NO T0 and NC T1 | Coil Q0 | Keep the LED ON during the second phase |

T0–T3 contacts read the timer's **done** bit, not whether it is currently counting. A TON starts timing when its condition becomes true. Its done bit becomes true when elapsed time reaches the preset, and remains true until its condition becomes false. A false condition resets elapsed time and the done bit. PT is preset time; ET is elapsed time. Timers run from elapsed clock time, not a loop counter; the logic has no blocking delays.

The two-timer oscillator includes reset scans between cycles. ON time is about 1000 ms; later OFF phases are about 1000 ms plus two scan intervals. With ideal 10 ms scans, transitions occur at 1000, 2000, 3020, 4020 ms, etc. GUI and hardware timing vary with scheduling; this is a scan-based demonstration, not a precision waveform generator.

For a physical LED, connect **GPIO18 → 330 Ω resistor → LED anode**, with **LED cathode → GND**. Reflash the included v0.3 sketch, close Arduino Serial Monitor, then use **Connect → Blink LED → Upload ladder → RUN**. You may also open `example_led_blink.json` instead of pressing Blink LED. Do not assume the built-in board LED uses GPIO18.

## 2. Flash the ESP32 runtime once

The included pin map targets a classic ESP32-WROOM-32 development board, not ESP32-C3/S3 boards. Check your board pinout and change the pin arrays if necessary.

1. In Arduino IDE install the **esp32 by Espressif Systems** board package.
2. Open `firmware/ESP32_Ladder/ESP32_Ladder.ino`. Keep `plc_core.h` beside it.
3. Select the correct ESP32 board and USB COM port.
4. Compile and upload the sketch. It uses no third-party Arduino libraries.
5. Close Arduino Serial Monitor so the desktop editor can use the COM port.

The firmware uses only ordinary `pinMode`, `digitalRead`, `digitalWrite`, `millis` and `Serial` APIs.

## 3. Wire a low-voltage bench demonstration

| Tag | GPIO | Connection / meaning |
|---|---:|---|
| I0 | 25 | START button between GPIO and GND |
| I1 | 26 | STOP button between GPIO and GND |
| I2 | 27 | SENSOR demonstration button between GPIO and GND |
| I3 | 32 | Extra button between GPIO and GND |
| Q0 | 18 | GPIO → 330 Ω resistor → LED anode; LED cathode → GND |
| Q1 | 19 | Same LED connection |
| Q2 | 21 | Same LED connection |
| Q3 | 22 | Same LED connection |
| M0–M7 | — | Internal Boolean memory; no physical pin |

Inputs use internal pull-ups: **button released = logical 0; button pressed = logical 1**. Input polarity is applied before ladder logic. An NC ladder contact is therefore true when its logical tag is 0; this does not mean the connected physical button must be an NC button.

GPIO inputs are 3.3 V signals. A 24 V PLC sensor needs an appropriate input interface. A motor or relay coil needs a driver; do not connect it directly to a GPIO. Begin with buttons and LEDs. The example STOP button is a software input, not a safety-rated emergency stop.

## 4. Upload and run your ladder

Install optional serial support:

```bat
py -m pip install -r requirements.txt
py app.py
```

Choose the ESP32 COM port and press **Connect → Upload ladder → RUN**. Green ladder contacts and the tag watch show online values. Online input checkboxes cannot force GPIO values; press the actual buttons. Press **STOP** to clear all outputs and M bits.

Edits stop the connected board. Upload the revised project before RUN. Connect also sends STOP, and closing/disconnecting attempts to send STOP. The runtime can continue independently if the USB link fails while running; loss of monitoring is not a confirmed stop. The runtime reports tag state every time the PC polls it, roughly five times per second.

## Defined execution behavior

- Target scan period: approximately 10 ms on ESP32, not a hard real-time guarantee. Desktop simulation is scheduled approximately every 10 ms; the display refreshes approximately every 100 ms.
- Each scan reads physical inputs into an input image, evaluates rungs top to bottom, then writes GPIO outputs.
- Q and M assignments are visible immediately to subsequent rungs. A self-holding contact reads the previous value until that rung writes its coil.
- One writer per Q, M or T tag. Up to four branches per rung, eight contacts per complete path. Storage capacity is 16 rungs: up to 12 Q/M coils and four TON timers.
- RUN continues from current state. STOP clears Q, M, timer done bits and elapsed times. Inputs continue to update while stopped.
- Boot always starts in STOP with no ladder program. Uploaded programs exist **only in RAM**. Power cycling or resetting requires uploading again.
- Upload uses staging: BEGIN stops the PLC; a valid COMMIT replaces the program. Any rejected rung or oversized serial line prevents commit. Failed upload leaves the prior program stored but stopped. Start a new BEGIN to retry.
- Basic contacts are not debounced in this version. Add debounce before introducing edge-sensitive counter instructions later.

## USB protocol (115200 baud, ASCII, newline terminated)

| Command | Successful reply | Purpose |
|---|---|---|
| `PING` | `PONG ESP32_LADDER_V2` | Identify compatible firmware |
| `BEGIN` | `OK BEGIN` | Stop, clear staging |
| `R Q0 I0,!I1;Q0,!I1` | `OK R` | Add rung; commas = AND, semicolons = OR, ! = NC |
| `T T0 1000 !T1` | `OK T` | Add a TON timer; preset is in milliseconds |
| `COMMIT` | `OK COMMIT` | Activate valid staging program, remain STOPPED |
| `RUN` | `OK RUN` | Start scan execution |
| `STOP` | `OK STOP` | Stop and clear Q/M |
| `STATE` | `STATE run inputs outputs memory scans timers et0 et1 et2 et3` | Decimal bit masks, scan count and elapsed times in ms |

Unknown/invalid commands return `ERR ...`. A STATE input mask of 5 means I0 and I2 are true. The protocol is intentionally local and simple; it has no authentication, Wi-Fi transport or project readback.

## Suggested development sequence

1. Validate the supplied editor/runtime on your exact board.
2. Add TOF/TP timers with elapsed-time semantics shared by simulator and ESP32.
3. Add rising-edge counters with explicit reset and debounce behavior.
4. Add pin configuration, persistent program storage and startup settings.
5. Add Modbus TCP and analogue scaling for sensor applications.
6. Package the desktop app as a Windows EXE after hardware verification.

## Validation and limits

`tests/test_model.py` checks desktop holding behavior, NC stop, shared-contact branching, rung ordering, stop reset, project validation, serialization, TON boundaries, 32-bit clock wrap and sustained blink phases. `tests/test_firmware.cpp` compiles the actual firmware against native Arduino stand-ins and checks GPIO behavior, scan execution, upload staging, malformed rungs, oversized serial input and equivalent timer/blink behavior. This validates logic and protocol behavior, not scheduling or electrical operation on a real ESP32.

```text
python -m unittest discover -s tests -p "test_*.py"
g++ -std=c++11 -Wall -Wextra -pedantic tests/test_firmware.cpp -o test_firmware
./test_firmware
```

The Arduino ESP32 target build, physical USB connection and desktop rendering on Windows have not been verified in this environment. Check those before extending this into a machine-control project.
