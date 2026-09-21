# Recovery — H3C Magic RT3000 (Machine-B)

The RT3000 keeps two firmware slots:

- the **OEM slot**, holding the original H3C firmware
- the **QSDK slot**, where this firmware is installed

A hardware selector stored in redundant configuration blocks decides which slot
boots. Because the two slots are independent, installing this firmware does not
erase the OEM firmware, and the device can be returned to it.

## Returning to the OEM firmware

The supported path is the slot switch exposed by the installed system. It
updates both redundant copies of the selector and reboots into the OEM slot.

Before switching, confirm the OEM slot is still intact. If your installed
firmware reports the OEM slot as invalid, stop and do not switch — booting a
damaged slot is worse than staying where you are.

## If the device will not boot

1. **Nothing on the console, no network** — the device may be in a slot whose
   image is damaged. Recovery requires the serial console.
2. **Serial console available** — the bootloader has a recovery path that can
   write a firmware image. This requires a TTL adapter and physical access.

Low-level procedures for writing the selector blocks directly are deliberately
not published here. They are easy to get wrong in a way that leaves the device
unbootable, and they are not needed for normal installation or recovery.

## What recovery cannot fix

- A damaged bootloader or a corrupted calibration partition is outside the
  scope of slot recovery and needs low-level flashing over the serial console.
- Once the OEM slot has been overwritten, this firmware provides no way to
  restore it.
