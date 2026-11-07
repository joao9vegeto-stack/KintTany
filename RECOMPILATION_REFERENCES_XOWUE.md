# XOWUE — recompilation and iOS input references

These repositories were consulted as engineering references; their code was not transplanted wholesale.

- [NFSMW Recompiled iOS](https://github.com/bep1s69/nfsmw-ios): static ARM64 iOS port and UIKit touch surface with explicit touchesBegan, touchesMoved, touchesEnded, touchesCancelled and targeted hit testing.
- [Theft4 / LibertyRecomp](https://github.com/KoreanSeats1/Theft4): Xbox 360 static AOT recompilation for iOS and host/runtime integration.
- [MW2 Recompiled](https://github.com/PaulCombal/mw2-recompiled): guest thread, kernel, filesystem and XAM/XInput runtime contracts for an Xbox 360 recompile.
- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp): shared Xbox 360 AOT runtime architecture and title/runtime boundary.
- [Xenia](https://github.com/xenia-project/xenia): reference implementation for XAM/XInput, kernel waits, file I/O and guest synchronization.
- [Sonic Free Riders iOS](https://github.com/DevZer0D4Y/SonicFreeRiders-iOS): ARM64 iOS port, touch/controller integration and Vulkan-on-Metal architecture.

The adopted design principle is to use small UIKit-backed control surfaces with independent touch lifetimes and exact hit regions, rather than full-screen transparent SwiftUI gesture containers over the rendered game. Xbox kernel semantics remain implemented and validated within XOWUE rather than copied without checking the title's contracts.
