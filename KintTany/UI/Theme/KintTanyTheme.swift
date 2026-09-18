import SwiftUI

enum KintTanyTheme {
    static let backgroundTop = Color(red: 0.025, green: 0.075, blue: 0.13)
    static let backgroundBottom = Color(red: 0.008, green: 0.02, blue: 0.045)
    static let panel = Color(red: 0.035, green: 0.09, blue: 0.145)
    static let panelRaised = Color(red: 0.055, green: 0.13, blue: 0.195)
    static let cyan = Color(red: 0.22, green: 0.91, blue: 1.0)
    static let gold = Color(red: 1.0, green: 0.73, blue: 0.22)
    static let border = Color(red: 0.18, green: 0.52, blue: 0.66)
    static let mutedText = Color(red: 0.58, green: 0.71, blue: 0.79)
    static let cornerRadius: CGFloat = 16
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

