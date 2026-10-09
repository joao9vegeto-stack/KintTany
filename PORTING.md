# Sonora IPA 1.1.1 → Android feature map

Evidence from `Payload/Sonora.app/Info.plist`, localized resource keys,
executable symbol names and included JavaScript files.

| Sonora (iOS) | Android v0.1 baseline | Status |
| --- | --- | --- |
| SwiftUI navigation / Inicio, Buscar, Biblioteca | Material 3 native Compose navigation | Equivalent function, different layout |
| YouTube Music / InnerTube search | Metrolist Android InnerTube | Available, subject to service availability |
| Swift AVPlayer audio | Android Media3 / ExoPlayer | Available |
| Audio in background | Android MediaSession + foreground service | Available |
| Playback queue / autoplay | Native player queue | Available |
| Offline download/cache | Metrolist Android cache | Available |
| Likes / playlists / library | Native local music library | Available |
| Synced lyrics | Lyrics source in Android client | Available when service supplies them |
| Account sign-in | Android login functionality | Login state not migrated |
| CarPlay | Android Auto integration depends on Android support | Not guaranteed |
| Sonora BPM AutoMix / MixEngine | No equivalent proven | NOT ported |
| Sonora's PO-token JS solver | Independent upstream extraction strategy | NOT ported |
| Sonora branding/UI icons | Original SpotiJon adaptive icon | New creation |

Not tested physically. This is explicitly NOT a translation of ARM64 Mach-O
or a recovered Swift source tree. The user-owned IPA is not shipped. This is a native Android recreation baseline based on an independent open-source codebase, not a source translation.
