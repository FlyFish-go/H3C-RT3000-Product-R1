# IPv6 firewall migration check

`96-rt3000-firewall-icmpv6` was checked on the host with the target busybox
and uci from a built rootfs under `qemu-arm-static`:

1. r9 product firewall + `wan6` interface: `wan6` added to the wan zone,
   `Allow-ICMPv6-Input` and `Allow-ICMPv6-Forward` added; a second run
   changes nothing.
2. r10 product firewall: unchanged.
3. No `wan6` interface: rules added, zone unchanged.
4. No zone named `wan` (operator renamed it): unchanged.
