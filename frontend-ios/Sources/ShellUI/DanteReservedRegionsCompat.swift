import SwiftUI

/// Compatibility adapter for the Xcode 27.1 SwiftUI SDK used by the bootstrap runner.
/// That SDK does not expose GeometryProxy.reservedRegions(kind:), even though
/// current NX2Apple source references it behind a runtime #available guard.
/// The empty result is the same non-divided fallback used before iOS/macOS 27.1.
/// This is intentionally distinct from the real API to avoid overload ambiguity.
enum DanteReservedDivisionKind {
    case division
}

struct DanteReservedDivision {
    let frame: CGRect
}

extension GeometryProxy {
    func danteReservedRegions(kind: DanteReservedDivisionKind) -> [DanteReservedDivision] {
        []
    }
}
