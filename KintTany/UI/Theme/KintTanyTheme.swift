import SwiftUI

enum KintTanyTheme {
    static let backgroundTop = Color(red: 0.018, green: 0.065, blue: 0.115)
    static let backgroundBottom = Color(red: 0.003, green: 0.013, blue: 0.032)
    static let panel = Color(red: 0.018, green: 0.070, blue: 0.120)
    static let panelRaised = Color(red: 0.030, green: 0.105, blue: 0.165)
    static let panelDeep = Color(red: 0.006, green: 0.028, blue: 0.055)
    static let cyan = Color(red: 0.10, green: 0.86, blue: 1.0)
    static let green = Color(red: 0.18, green: 0.95, blue: 0.48)
    static let red = Color(red: 1.0, green: 0.24, blue: 0.31)
    static let gold = Color(red: 1.0, green: 0.72, blue: 0.16)
    static let orange = Color(red: 1.0, green: 0.43, blue: 0.13)
    static let border = Color(red: 0.13, green: 0.50, blue: 0.68)
    static let mutedText = Color(red: 0.59, green: 0.74, blue: 0.84)
    static let cornerRadius: CGFloat = 12
}

extension ActivityMode {
    var artworkName: String {
        switch self {
        case .tree: "ActivityWood"
        case .coal: "ActivityCoal"
        case .stone: "ActivityStone"
        case .iron: "ActivityIron"
        case .silver: "ActivitySilver"
        case .cacti: "ActivityCacti"
        case .fishing: "ActivityFishing"
        case .chicken: "ActivityChicken"
        case .zombie: "ActivityZombie"
        case .dragon: "ActivityDragon"
        }
    }

    var categoryLabel: String {
        switch self {
        case .fishing: "PESCA"
        case .chicken, .zombie, .dragon: "COMBATE"
        default: "COLETA"
        }
    }

    var activityDescription: String {
        switch self {
        case .tree: "Coleta de madeira"
        case .coal: "Mineração de carvão"
        case .stone: "Mineração de pedra"
        case .iron: "Mineração de Iron Ore"
        case .silver: "Mineração de Silver Ore"
        case .cacti: "Coleta de Cacti"
        case .fishing: "Pesca automatizada"
        case .chicken: "Combate contra galinhas"
        case .zombie: "Combate contra zumbis"
        case .dragon: "Combate contra dragões"
        }
    }
}
