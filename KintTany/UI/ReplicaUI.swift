import Foundation
import SwiftUI
import UIKit

public enum KintActivity: String, CaseIterable, Identifiable, Sendable {
    case idle
    case wood
    case coal
    case stone
    case ironOre
    case silverOre
    case cacti
    case fishing
    case roastPit
    case chicken
    case zombie
    case dragon

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .idle: "Aguardando atividade"
        case .wood: "Madeira"
        case .coal: "Carvão"
        case .stone: "Pedra"
        case .ironOre: "Iron Ore"
        case .silverOre: "Silver Ore"
        case .cacti: "Cacti"
        case .fishing: "Pesca"
        case .roastPit: "Roast Pit"
        case .chicken: "Galinha"
        case .zombie: "Zumbi"
        case .dragon: "Dragão"
        }
    }

    public var assetName: String {
        switch self {
        case .idle: ""
        case .wood: "KintWood"
        case .coal: "KintCoal"
        case .stone: "KintStone"
        case .ironOre: "KintIronOre"
        case .silverOre: "KintSilverOre"
        case .cacti: "KintCacti"
        case .fishing: "KintFishing"
        case .roastPit: "KintFishing"
        case .chicken: "KintChicken"
        case .zombie: "KintZombie"
        case .dragon: "KintDragon"
        }
    }

    public var headerTitle: String {
        switch self {
        case .idle: "Aguardando atividade"
        case .stone: "Pedra"
        case .ironOre: "Iron Ore"
        case .silverOre: "Silver Ore"
        default: title
        }
    }
}

public struct KintSkill: Identifiable, Hashable, Sendable {
    public var id: String { name }
    public var name: String
    public var value: Int
    public var maximum: Int

    public init(name: String, value: Int, maximum: Int = 40) {
        self.name = name
        self.value = value
        self.maximum = max(1, maximum)
    }

    public var fraction: Double {
        min(1, max(0, Double(value) / Double(maximum)))
    }
}

public struct KintLocationSummary: Hashable, Sendable {
    public var region: String
    public var position: String
    public var resources: Int
    public var mobs: Int
    public var lastEvent: String

    public init(
        region: String,
        position: String,
        resources: Int,
        mobs: Int,
        lastEvent: String
    ) {
        self.region = region
        self.position = position
        self.resources = resources
        self.mobs = mobs
        self.lastEvent = lastEvent
    }
}

public struct KintSessionSummary: Hashable, Sendable {
    public var target: Int
    public var successes: Int
    public var failures: Int
    public var attempts: Int

    public init(target: Int, successes: Int, failures: Int, attempts: Int) {
        self.target = target
        self.successes = successes
        self.failures = failures
        self.attempts = attempts
    }
}

public enum KintDashboardTab: String, CaseIterable, Identifiable, Sendable {
    case stats = "STATS"
    case quests = "QUESTS"
    case session = "SESSÃO"

    public var id: String { rawValue }
}

public struct KintTanyDashboardState: Hashable, Sendable {
    public var isOnline: Bool
    public var selectedActivity: KintActivity
    public var activityTitle: String
    public var completed: Int
    public var target: Int
    public var actionProgress: Int
    public var actionRequirement: Int
    public var rateText: String
    public var statusText: String
    public var skills: [KintSkill]
    public var totalLevel: Int
    public var totalLevelMaximum: Int
    public var location: KintLocationSummary
    public var session: KintSessionSummary
    public var isRunning: Bool
    public var isPaused: Bool
    public var selectedTab: KintDashboardTab

    public init(
        isOnline: Bool,
        selectedActivity: KintActivity,
        activityTitle: String? = nil,
        completed: Int,
        target: Int,
        actionProgress: Int,
        actionRequirement: Int,
        rateText: String,
        statusText: String,
        skills: [KintSkill],
        totalLevel: Int,
        totalLevelMaximum: Int = 240,
        location: KintLocationSummary,
        session: KintSessionSummary,
        isRunning: Bool,
        isPaused: Bool,
        selectedTab: KintDashboardTab = .stats
    ) {
        self.isOnline = isOnline
        self.selectedActivity = selectedActivity
        self.activityTitle = activityTitle ?? selectedActivity.headerTitle
        self.completed = completed
        self.target = max(1, target)
        self.actionProgress = actionProgress
        self.actionRequirement = max(1, actionRequirement)
        self.rateText = rateText
        self.statusText = statusText
        self.skills = skills
        self.totalLevel = totalLevel
        self.totalLevelMaximum = max(1, totalLevelMaximum)
        self.location = location
        self.session = session
        self.isRunning = isRunning
        self.isPaused = isPaused
        self.selectedTab = selectedTab
    }

    public static let referenceSample = KintTanyDashboardState(
        isOnline: false,
        selectedActivity: .idle,
        activityTitle: "Aguardando atividade",
        completed: 0,
        target: 100,
        actionProgress: 0,
        actionRequirement: 100,
        rateText: "0.00/min",
        statusText: "Pronto",
        skills: [
            .init(name: "Combat", value: 0),
            .init(name: "Wood", value: 0),
            .init(name: "Mining", value: 0),
            .init(name: "Fishing", value: 0),
            .init(name: "Cooking", value: 0),
            .init(name: "Smithing", value: 0),
        ],
        totalLevel: 0,
        totalLevelMaximum: 100,
        location: .init(region: "—", position: "—", resources: 0, mobs: 0, lastEvent: "—"),
        session: .init(target: 100, successes: 0, failures: 0, attempts: 0),
        isRunning: false,
        isPaused: false,
        selectedTab: .stats
    )
}

public struct KintTanyDashboardActions {
    public var selectActivity: (KintActivity) -> Void
    public var togglePause: () -> Void
    public var selectTab: (KintDashboardTab) -> Void
    public var openFullLog: () -> Void
    public var editTarget: () -> Void
    public var decrementTarget: () -> Void
    public var incrementTarget: () -> Void

    public init(
        selectActivity: @escaping (KintActivity) -> Void = { _ in },
        togglePause: @escaping () -> Void = {},
        selectTab: @escaping (KintDashboardTab) -> Void = { _ in },
        openFullLog: @escaping () -> Void = {},
        editTarget: @escaping () -> Void = {},
        decrementTarget: @escaping () -> Void = {},
        incrementTarget: @escaping () -> Void = {}
    ) {
        self.selectActivity = selectActivity
        self.togglePause = togglePause
        self.selectTab = selectTab
        self.openFullLog = openFullLog
        self.editTarget = editTarget
        self.decrementTarget = decrementTarget
        self.incrementTarget = incrementTarget
    }

    public static let inert = KintTanyDashboardActions()
}

public enum KintReplicaSizingMode: Equatable, Sendable {
    /// Keeps the reference's exact 9:16 geometry and centers it when needed.
    case aspectFit
    /// Fills the available frame. Use only when the host already has a 9:16 canvas.
    case fill
}

public enum KintTanyTheme {
    public static let canvasSize = CGSize(width: 390, height: 760)

    public static let surface = Color(red: 218 / 255, green: 211 / 255, blue: 202 / 255)
    public static let surfaceHighlight = Color(red: 235 / 255, green: 231 / 255, blue: 225 / 255)
    public static let surfaceShadow = Color(red: 164 / 255, green: 155 / 255, blue: 145 / 255)
    public static let ink = Color(red: 43 / 255, green: 40 / 255, blue: 37 / 255)
    public static let mutedInk = Color(red: 103 / 255, green: 96 / 255, blue: 88 / 255)
    public static let terracotta = Color(red: 170 / 255, green: 98 / 255, blue: 73 / 255)
    public static let terracottaHighlight = Color(red: 205 / 255, green: 128 / 255, blue: 94 / 255)
    public static let terracottaShadow = Color(red: 111 / 255, green: 57 / 255, blue: 40 / 255)
    public static let online = Color(red: 118 / 255, green: 136 / 255, blue: 119 / 255)
    public static let divider = Color(red: 132 / 255, green: 124 / 255, blue: 115 / 255).opacity(0.82)

    public static func bodyFont(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("Helvetica Neue", size: size).weight(weight)
    }

    public static func titleFont(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("Helvetica Neue", size: size).weight(weight)
    }
}

extension View {
    func kintEmbossedText() -> some View {
        shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.95), radius: 0.25, x: 0, y: 0.8)
    }

    func kintRaised(radius: CGFloat, darkOffset: CGFloat = 2.0) -> some View {
        clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.95), radius: 2, x: -1.5, y: -1.5)
            .shadow(color: KintTanyTheme.surfaceShadow.opacity(0.72), radius: 2.5, x: darkOffset, y: darkOffset)
    }
}

enum KintResourceImage {
    static func image(_ name: String) -> Image {
        Image(name, bundle: .main)
    }
}

struct KintNotch: View {
    var body: some View {
        ZStack(alignment: .top) {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Color.black.opacity(0.88), Color(red: 33 / 255, green: 34 / 255, blue: 34 / 255)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(KintTanyTheme.surfaceShadow.opacity(0.8), lineWidth: 1)
                )
                .frame(width: 154, height: 34)
                .offset(y: -6)
        }
        .frame(width: 154, height: 29, alignment: .top)
        .clipped()
    }
}

struct KintStatusIcons: View {
    var body: some View {
        HStack(spacing: 8) {
            HStack(alignment: .bottom, spacing: 2) {
                ForEach(0..<4, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 1)
                        .fill(KintTanyTheme.ink)
                        .frame(width: 3, height: CGFloat(5 + index * 3))
                }
            }
            KintWifiGlyph()
                .frame(width: 19, height: 14)
            KintBatteryGlyph()
                .frame(width: 24, height: 12)
        }
        .foregroundStyle(KintTanyTheme.ink)
    }
}

struct KintWifiGlyph: View {
    var body: some View {
        Canvas { context, size in
            let center = CGPoint(x: size.width / 2, y: size.height + 1)
            for index in 0..<2 {
                let inset = CGFloat(index) * 4
                var path = Path()
                path.addArc(
                    center: center,
                    radius: size.width / 2 - inset,
                    startAngle: .degrees(215),
                    endAngle: .degrees(325),
                    clockwise: false
                )
                context.stroke(path, with: .color(KintTanyTheme.ink), style: .init(lineWidth: 1.6, lineCap: .round))
            }
            let dot = CGRect(x: center.x - 1.8, y: size.height - 3.5, width: 3.6, height: 3.6)
            context.fill(Path(ellipseIn: dot), with: .color(KintTanyTheme.ink))
        }
    }
}

struct KintBatteryGlyph: View {
    var body: some View {
        Canvas { context, size in
            let shell = CGRect(x: 0.5, y: 0.5, width: size.width - 3.5, height: size.height - 1)
            context.stroke(
                Path(roundedRect: shell, cornerRadius: 2),
                with: .color(KintTanyTheme.ink),
                lineWidth: 1.2
            )
            let level = CGRect(x: 3, y: 3, width: size.width - 9, height: size.height - 6)
            context.fill(Path(roundedRect: level, cornerRadius: 0.8), with: .color(KintTanyTheme.ink))
            let nub = CGRect(x: size.width - 2.2, y: size.height * 0.33, width: 2.2, height: size.height * 0.34)
            context.fill(Path(roundedRect: nub, cornerRadius: 0.7), with: .color(KintTanyTheme.ink))
        }
    }
}

struct KintDivider: View {
    var body: some View {
        Rectangle()
            .fill(KintTanyTheme.divider)
            .frame(height: 0.7)
            .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.95), radius: 0, x: 0, y: 0.8)
    }
}

struct KintInsetPanel<Content: View>: View {
    let cornerRadius: CGFloat
    let content: Content

    init(cornerRadius: CGFloat = 13, @ViewBuilder content: () -> Content) {
        self.cornerRadius = cornerRadius
        self.content = content()
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(KintTanyTheme.surface.opacity(0.92))
                .shadow(color: KintTanyTheme.surfaceShadow.opacity(0.72), radius: 3.2, x: 2.2, y: 2.4)
                .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.96), radius: 2.6, x: -2.2, y: -2.2)
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [KintTanyTheme.surfaceShadow.opacity(0.54), KintTanyTheme.surfaceHighlight.opacity(0.94)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1.1
                )
            content
        }
    }
}

public struct KintDefaultAvatarView: View {
    public init() {}

    public var body: some View {
        KintResourceImage.image("KintAvatar")
            .resizable()
            .interpolation(.high)
            .scaledToFit()
            .accessibilityLabel("Personagem")
    }
}

struct KintProgressDots: View {
    let completed: Int
    let target: Int
    private let count = 10

    private var activeCount: Int {
        guard completed > 0 else { return 0 }
        let fraction = min(1, max(0, Double(completed) / Double(max(1, target))))
        return max(1, min(count, Int(ceil(fraction * Double(count)))))
    }

    var body: some View {
        HStack(spacing: 5.0) {
            ForEach(0..<count, id: \.self) { index in
                Circle()
                    .fill(index < activeCount ? AnyShapeStyle(
                        LinearGradient(
                            colors: [KintTanyTheme.terracottaHighlight, KintTanyTheme.terracotta],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    ) : AnyShapeStyle(KintTanyTheme.surface))
                    .overlay(
                        Circle()
                            .stroke(
                                index < activeCount
                                    ? KintTanyTheme.terracottaShadow.opacity(0.72)
                                    : KintTanyTheme.surfaceShadow.opacity(0.78),
                                lineWidth: 0.8
                            )
                    )
                    .shadow(
                        color: index < activeCount
                            ? KintTanyTheme.terracottaShadow.opacity(0.45)
                            : KintTanyTheme.surfaceShadow.opacity(0.55),
                        radius: 1.2,
                        x: 1,
                        y: 1
                    )
                    .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.95), radius: 0.8, x: -0.8, y: -0.8)
                    .frame(width: 13.5, height: 13.5)
            }
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 3)
        .background(
            Capsule()
                .fill(KintTanyTheme.surface.opacity(0.84))
                .shadow(color: KintTanyTheme.surfaceShadow.opacity(0.7), radius: 2.3, x: 1.4, y: 1.7)
                .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.98), radius: 1.4, x: -1.2, y: -1.2)
        )
    }
}

struct KintActivityGridBackground: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(KintTanyTheme.surface.opacity(0.92))
            KintResourceImage.image("KintPaperTexture")
                .resizable(resizingMode: .tile)
                .opacity(0.52)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            KintResourceImage.image("KintActivityFrames10")
                .resizable()
                .interpolation(.high)
                .scaledToFill()
                .allowsHitTesting(false)
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [KintTanyTheme.surfaceHighlight.opacity(0.98), KintTanyTheme.surfaceShadow.opacity(0.76)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1.05
                )
        }
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .shadow(color: KintTanyTheme.surfaceShadow.opacity(0.48), radius: 2.2, x: 1.2, y: 1.4)
        .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.88), radius: 1.2, x: -0.7, y: -0.7)
    }
}

struct KintActivitySprite: View {
    let activity: KintActivity
    var body: some View {
        KintResourceImage.image(activity.assetName)
            .resizable()
            .interpolation(.high)
            .scaledToFit()
    }
}

struct KintExactActivityGrid: View {
    @Binding var selected: KintActivity
    let didSelect: (KintActivity) -> Void
    private let top: [KintActivity] = [.wood, .coal, .stone, .ironOre, .silverOre, .cacti]
    private let bottom: [KintActivity] = [.fishing, .roastPit, .chicken, .zombie, .dragon]

    var body: some View {
        ZStack {
            KintActivityGridBackground()
            VStack(spacing: 0) {
                activityRow(top)
                activityRow(bottom)
            }
            .padding(.top, 18)
            .padding(.bottom, 4)
        }
    }

    private func activityRow(_ activities: [KintActivity]) -> some View {
        HStack(spacing: 0) {
            ForEach(activities) { activity in
                Button {
                    selected = activity
                    didSelect(activity)
                } label: {
                    VStack(spacing: 1) {
                        KintActivitySprite(activity: activity).frame(width: 38, height: 34)
                        Text(activity.title)
                            .font(KintTanyTheme.bodyFont(7.7, weight: selected == activity ? .medium : .regular))
                            .foregroundStyle(KintTanyTheme.ink)
                            .lineLimit(1).minimumScaleFactor(0.68)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .contentShape(Rectangle())
                    .background(selected == activity ? KintTanyTheme.terracotta.opacity(0.08) : .clear)
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxHeight: .infinity)
    }
}

struct KintSkillBar: View {
    let skill: KintSkill

    var body: some View {
        HStack(spacing: 5) {
            Text(skill.name)
                .font(KintTanyTheme.bodyFont(12))
                .foregroundStyle(KintTanyTheme.ink)
                .frame(width: 66, alignment: .leading)
                .lineLimit(1)
                .minimumScaleFactor(0.76)
            KintProgressBar(fraction: skill.fraction)
                .frame(width: 118, height: 11.5)
            Text("\(skill.value)/\(skill.maximum)")
                .font(KintTanyTheme.bodyFont(11.2))
                .foregroundStyle(KintTanyTheme.ink)
                .frame(width: 39, alignment: .trailing)
        }
        .frame(height: 20.8)
    }
}

struct KintProgressBar: View {
    let fraction: Double

    var body: some View {
        GeometryReader { proxy in
            let clamped = min(1, max(0, fraction))
            let fillWidth = max(clamped > 0 ? 8 : 0, proxy.size.width * clamped)
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(KintTanyTheme.surface.opacity(0.92))
                    .shadow(color: KintTanyTheme.surfaceShadow.opacity(0.78), radius: 1.8, x: 1.1, y: 1.2)
                    .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.96), radius: 1.1, x: -0.9, y: -0.9)
                    .overlay(Capsule().stroke(KintTanyTheme.surfaceShadow.opacity(0.5), lineWidth: 0.7))
                KintResourceImage.image("KintButtonTexture")
                    .resizable(resizingMode: .tile)
                    .frame(width: fillWidth, height: proxy.size.height - 1.5)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(KintTanyTheme.terracottaShadow.opacity(0.65), lineWidth: 0.7))
            }
        }
    }
}

struct KintStatsPanel: View {
    let skills: [KintSkill]
    let totalLevel: Int
    let totalMaximum: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("STATS")
                .font(KintTanyTheme.titleFont(15.5, weight: .medium))
                .foregroundStyle(KintTanyTheme.ink)
                .kintEmbossedText()
                .frame(height: 24, alignment: .topLeading)
            ForEach(Array(skills.prefix(6))) { skill in
                KintSkillBar(skill: skill)
            }
            KintDivider()
                .padding(.leading, 68)
                .padding(.trailing, 1)
                .padding(.top, 1)
                .padding(.bottom, 4)
            HStack(spacing: 5) {
                Text("Total Level")
                    .font(KintTanyTheme.bodyFont(12))
                    .foregroundStyle(KintTanyTheme.ink)
                    .frame(width: 66, alignment: .leading)
                KintProgressBar(fraction: min(1, max(0, Double(totalLevel) / Double(max(1, totalMaximum)))))
                    .frame(width: 118, height: 11.5)
                Text("\(totalLevel)")
                    .font(KintTanyTheme.bodyFont(11.2))
                    .foregroundStyle(KintTanyTheme.ink)
                    .frame(width: 39, alignment: .trailing)
            }
        }
    }
}

enum KintRegionArtwork {
    static func assetName(for rawRegion: String) -> String {
        let key = rawRegion
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: " ", with: "_")
        if key.contains("bank") { return "KintRegionBankShop" }
        if key.hasPrefix("wild") { return "KintRegionWild" }
        switch key {
        case "world": return "KintRegionWorld"
        case "eldergrove": return "KintRegionEldergrove"
        case "frostmere": return "KintRegionFrostmere"
        case "pond": return "KintRegionPond"
        case "beach", "the_shores", "shores": return "KintRegionBeach"
        case "desert": return "KintRegionDesert"
        case "desert_west": return "KintRegionDesertWest"
        case "desert_south": return "KintRegionDesertSouth"
        default: return "KintRegionUnknown"
        }
    }
}

struct KintLocationPanel: View {
    let location: KintLocationSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4.1) {
            KintResourceImage.image(KintRegionArtwork.assetName(for: location.region))
                .resizable()
                .interpolation(.high)
                .scaledToFit()
                .frame(width: 62, height: 42)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.bottom, 1)

            telemetryLine("Região \(location.region)")
            telemetryLine("Posição \(location.position)")
            telemetryLine("Recursos \(location.resources)")
            telemetryLine("Mobs \(location.mobs)")

            Text("Último evento \(location.lastEvent)")
                .font(KintTanyTheme.bodyFont(9.7))
                .foregroundStyle(KintTanyTheme.ink)
                .lineLimit(2)
                .minimumScaleFactor(0.68)
                .allowsTightening(true)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(KintTanyTheme.ink)
        .kintEmbossedText()
    }

    private func telemetryLine(_ value: String) -> some View {
        Text(value)
            .font(KintTanyTheme.bodyFont(10.2))
            .lineLimit(1)
            .minimumScaleFactor(0.56)
            .allowsTightening(true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct KintMetricCell: View {
    let title: String
    let value: Int

    var body: some View {
        VStack(spacing: 4) {
            Text(title)
                .font(KintTanyTheme.bodyFont(11.5))
                .foregroundStyle(KintTanyTheme.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Text("\(value)")
                .font(KintTanyTheme.titleFont(18))
                .foregroundStyle(KintTanyTheme.ink)
        }
        .kintEmbossedText()
        .frame(maxWidth: .infinity)
    }
}

struct KintSessionCounters: View {
    let session: KintSessionSummary
    let editTarget: () -> Void
    let decrementTarget: () -> Void
    let incrementTarget: () -> Void
    let targetEnabled: Bool

    var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: 3) {
                selectorButton(mirrored: true, action: decrementTarget)

                Button(action: editTarget) {
                    KintMetricCell(title: "Meta da sessão", value: session.target)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!targetEnabled)

                selectorButton(mirrored: false, action: incrementTarget)
            }
            .frame(width: 118)
            separator
            KintMetricCell(title: "Sucessos", value: session.successes)
            separator
            KintMetricCell(title: "Falhas", value: session.failures)
            separator
            KintMetricCell(title: "Tentativas", value: session.attempts)
        }
    }

    private func selectorButton(mirrored: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            KintResourceImage.image("KintMetaArrow")
                .resizable()
                .interpolation(.high)
                .scaledToFit()
                .scaleEffect(x: mirrored ? -1 : 1, y: 1)
                .frame(width: 24, height: 32)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!targetEnabled)
        .opacity(targetEnabled ? 1 : 0.32)
        .accessibilityLabel(mirrored ? "Diminuir meta" : "Aumentar meta")
    }

    private var separator: some View {
        Rectangle()
            .fill(KintTanyTheme.divider)
            .frame(width: 0.75, height: 40)
            .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.85), radius: 0, x: 0.7, y: 0)
    }
}

struct KintPauseButton: View {
    let isRunning: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 18) {
                RoundedRectangle(cornerRadius: 2.2, style: .continuous)
                    .fill(KintTanyTheme.surfaceHighlight)
                    .overlay(RoundedRectangle(cornerRadius: 2.2).stroke(KintTanyTheme.terracottaShadow.opacity(0.8), lineWidth: 0.8))
                    .frame(width: 22, height: 22)
                Text("PARAR")
                    .font(KintTanyTheme.titleFont(16.5, weight: .medium))
                    .tracking(0.7)
            }
            .foregroundStyle(KintTanyTheme.surfaceHighlight)
            .shadow(color: KintTanyTheme.terracottaShadow.opacity(0.9), radius: 0.6, x: 0.8, y: 1)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(ZStack {
                KintTanyTheme.terracotta
                KintResourceImage.image("KintButtonTexture").resizable(resizingMode: .tile).opacity(0.62)
            })
            .overlay(RoundedRectangle(cornerRadius: 13.5).stroke(KintTanyTheme.terracottaShadow, lineWidth: 1.3))
            .kintRaised(radius: 13.5, darkOffset: 2.5)
            .opacity(isRunning ? 1 : 0.42)
        }
        .buttonStyle(.plain)
        .disabled(!isRunning)
        .accessibilityLabel("Parar")
    }
}

struct KintTabBar: View {
    @Binding var selection: KintDashboardTab
    let didSelect: (KintDashboardTab) -> Void

    var body: some View {
        HStack(spacing: 0) {
            tab(.stats, systemName: "chart.bar.fill")
            separator
            tab(.quests, systemName: "list.bullet")
            separator
            tab(.session, systemName: "slider.horizontal.3")
        }
        .foregroundStyle(KintTanyTheme.ink)
    }

    private func tab(_ tab: KintDashboardTab, systemName: String) -> some View {
        Button {
            selection = tab
            didSelect(tab)
        } label: {
            HStack(spacing: 8) {
                Image(systemName: systemName)
                    .font(.system(size: 18, weight: .regular))
                    .frame(width: 22)
                Text(tab.rawValue)
                    .font(KintTanyTheme.bodyFont(12, weight: selection == tab ? .medium : .regular))
                    .tracking(0.25)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
            .opacity(selection == tab ? 1 : 0.88)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selection == tab ? [.isSelected] : [])
    }

    private var separator: some View {
        Rectangle()
            .fill(KintTanyTheme.divider)
            .frame(width: 0.75, height: 26)
            .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.95), radius: 0, x: 0.8, y: 0)
    }
}

struct KintLogRow: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: "list.clipboard")
                    .font(.system(size: 20, weight: .regular))
                    .frame(width: 25)
                Text("Log completo")
                    .font(KintTanyTheme.bodyFont(13.2))
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 18, weight: .medium))
            }
            .foregroundStyle(KintTanyTheme.ink)
            .padding(.horizontal, 15)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

public struct KintTanyDashboardView<AvatarContent: View>: View {
    @Binding private var state: KintTanyDashboardState
    private let sizingMode: KintReplicaSizingMode
    private let actions: KintTanyDashboardActions
    private let avatar: AvatarContent
    private let referenceOverlayOpacity: Double

    public init(
        state: Binding<KintTanyDashboardState>,
        sizingMode: KintReplicaSizingMode = .aspectFit,
        actions: KintTanyDashboardActions = .inert,
        referenceOverlayOpacity: Double = 0,
        @ViewBuilder avatar: () -> AvatarContent
    ) {
        _state = state
        self.sizingMode = sizingMode
        self.actions = actions
        self.avatar = avatar()
        self.referenceOverlayOpacity = min(1, max(0, referenceOverlayOpacity))
    }

    public var body: some View {
        GeometryReader { proxy in
            let sx = proxy.size.width / KintTanyTheme.canvasSize.width
            let sy = proxy.size.height / KintTanyTheme.canvasSize.height
            let fitScale = min(sx, sy)
            let scaleX = sizingMode == .fill ? sx : fitScale
            let scaleY = sizingMode == .fill ? sy : fitScale
            let renderedWidth = KintTanyTheme.canvasSize.width * scaleX
            let renderedHeight = KintTanyTheme.canvasSize.height * scaleY
            let offsetX = max(0, (proxy.size.width - renderedWidth) / 2)
            let offsetY = max(0, (proxy.size.height - renderedHeight) / 2)

            ZStack(alignment: .topLeading) {
                KintTanyTheme.surface.ignoresSafeArea()
                KintTanyDesignCanvas(
                    state: $state,
                    actions: actions,
                    avatar: avatar,
                    referenceOverlayOpacity: referenceOverlayOpacity
                )
                .frame(width: KintTanyTheme.canvasSize.width, height: KintTanyTheme.canvasSize.height)
                .scaleEffect(x: scaleX, y: scaleY, anchor: .topLeading)
                .offset(x: offsetX, y: offsetY)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .background(KintTanyTheme.surface)
        .accessibilityElement(children: .contain)
    }
}

public extension KintTanyDashboardView where AvatarContent == KintDefaultAvatarView {
    init(
        state: Binding<KintTanyDashboardState>,
        sizingMode: KintReplicaSizingMode = .aspectFit,
        actions: KintTanyDashboardActions = .inert,
        referenceOverlayOpacity: Double = 0
    ) {
        self.init(
            state: state,
            sizingMode: sizingMode,
            actions: actions,
            referenceOverlayOpacity: referenceOverlayOpacity
        ) {
            KintDefaultAvatarView()
        }
    }
}

private struct KintTanyDesignCanvas<AvatarContent: View>: View {
    @Binding var state: KintTanyDashboardState
    let actions: KintTanyDashboardActions
    let avatar: AvatarContent
    let referenceOverlayOpacity: Double

    var body: some View {
        ZStack(alignment: .topLeading) {
            shell
            header
            topContent
            statistics
            session
            controls

            if referenceOverlayOpacity > 0 {
                KintResourceImage.image("KintFullReference")
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 390, height: 760)
                    .opacity(referenceOverlayOpacity)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .frame(width: 390, height: 760)
        .clipped()
    }

    private var shell: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 36, style: .continuous)
                .fill(KintTanyTheme.surface)
            KintResourceImage.image("KintPaperTexture")
                .resizable(resizingMode: .tile)
                .opacity(0.54)
                .clipShape(RoundedRectangle(cornerRadius: 36, style: .continuous))
            RoundedRectangle(cornerRadius: 36, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [KintTanyTheme.surfaceHighlight, KintTanyTheme.surfaceShadow.opacity(0.82)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 2.2
                )
        }
        .shadow(color: Color.black.opacity(0.3), radius: 8, x: 2, y: 5)
        .frame(width: 388, height: 756)
        .position(x: 195, y: 380)
    }

    private var header: some View {
        Group {
            HStack(spacing: 7) {
                KintResourceImage.image("KintOnlineDot")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 15, height: 15)
                    .saturation(state.isOnline ? 1 : 0)
                    .opacity(state.isOnline ? 1 : 0.5)
                Text(state.isOnline ? "ONLINE" : "OFFLINE")
                    .font(KintTanyTheme.bodyFont(14))
                Spacer()
                Text("KintTany")
                    .font(KintTanyTheme.titleFont(24))
                Spacer()
                Color.clear.frame(width: 82, height: 1)
            }
            .foregroundStyle(KintTanyTheme.ink)
            .kintEmbossedText()
            .frame(width: 350, height: 38)
            .position(x: 195, y: 35)

            KintDivider()
                .frame(width: 350)
                .position(x: 195, y: 61)
        }
    }

    private var topContent: some View {
        Group {
            KintInsetPanel(cornerRadius: 13) {
                avatar
                    .padding(.horizontal, 6)
                    .padding(.vertical, 10)
            }
            .frame(width: 96, height: 238)
            .position(x: 62, y: 184)

            HStack(alignment: .firstTextBaseline) {
                Text(state.activityTitle)
                    .font(KintTanyTheme.titleFont(20))
                    .lineLimit(1)
                    .minimumScaleFactor(0.68)
                Spacer()
                Text("\(state.completed)/\(state.target)")
                    .font(KintTanyTheme.titleFont(18))
                    .contentShape(Rectangle())
                    .onTapGesture { actions.editTarget() }
            }
            .foregroundStyle(KintTanyTheme.ink)
            .kintEmbossedText()
            .frame(width: 238, height: 27)
            .position(x: 253, y: 82)

            KintProgressDots(completed: state.completed, target: state.target)
                .frame(width: 235, height: 22)
                .position(x: 253, y: 109)

            HStack(spacing: 6) {
                Text("Progresso \(state.actionProgress)/\(state.actionRequirement) • \(state.rateText)")
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                    .allowsTightening(true)
                    .layoutPriority(1)
                Spacer(minLength: 4)
                Text(state.statusText)
                    .lineLimit(1)
                    .minimumScaleFactor(0.48)
                    .allowsTightening(true)
                    .frame(maxWidth: 112, alignment: .trailing)
            }
            .font(KintTanyTheme.bodyFont(10.8))
            .foregroundStyle(KintTanyTheme.ink)
            .kintEmbossedText()
            .frame(width: 238, height: 20)
            .position(x: 253, y: 136)

            KintExactActivityGrid(
                selected: $state.selectedActivity,
                didSelect: actions.selectActivity
            )
            .frame(width: 246, height: 172)
            .position(x: 253, y: 238)

            KintDivider()
                .frame(width: 350)
                .position(x: 195, y: 326)
        }
    }

    private var statistics: some View {
        Group {
            KintStatsPanel(
                skills: state.skills,
                totalLevel: state.totalLevel,
                totalMaximum: state.totalLevelMaximum
            )
            .frame(width: 232, height: 179, alignment: .topLeading)
            .position(x: 136, y: 419.5)

            Rectangle()
                .fill(KintTanyTheme.divider)
                .frame(width: 0.75, height: 166)
                .shadow(color: KintTanyTheme.surfaceHighlight.opacity(0.95), radius: 0, x: 0.8, y: 0)
                .position(x: 254, y: 420)

            KintLocationPanel(location: state.location)
                .frame(width: 112, height: 174, alignment: .topLeading)
                .position(x: 314, y: 420)

            KintDivider()
                .frame(width: 350)
                .position(x: 195, y: 516)
        }
    }

    private var session: some View {
        Group {
            KintSessionCounters(
                session: state.session,
                editTarget: actions.editTarget,
                decrementTarget: actions.decrementTarget,
                incrementTarget: actions.incrementTarget,
                targetEnabled: !state.isRunning
            )
                .frame(width: 346, height: 48)
                .position(x: 195, y: 548.5)
        }
    }

    private var controls: some View {
        Group {
            KintPauseButton(isRunning: state.isRunning) {
                actions.togglePause()
            }
            .frame(width: 258, height: 53)
            .position(x: 195, y: 610.5)

            KintDivider()
                .frame(width: 350)
                .position(x: 195, y: 649)

            KintTabBar(selection: $state.selectedTab, didSelect: actions.selectTab)
                .frame(width: 346, height: 41)
                .position(x: 195, y: 672)

            KintDivider()
                .frame(width: 350)
                .position(x: 195, y: 694.5)

            KintLogRow(action: actions.openFullLog)
                .frame(width: 350, height: 47)
                .position(x: 195, y: 721)
        }
    }
}

/// The literal source image. Use it as the visual oracle and in screenshot tests;
/// use `KintTanyDashboardView` for the interactive production screen.
public struct KintTanyPixelReferenceView: View {
    public init() {}

    public var body: some View {
        KintResourceImage.image("KintFullReference")
            .resizable()
            .interpolation(.high)
            .scaledToFit()
            .accessibilityLabel("Referência visual KintTany")
    }
}

@MainActor
struct ReplicaDashboardHost: View {
    @EnvironmentObject private var app: AppStore

    @Binding var showLogin: Bool
    @Binding var showFullLog: Bool
    @Binding var showCharacterStats: Bool
    @Binding var showDailyQuests: Bool

    @State private var dashboard = KintTanyDashboardState.referenceSample
    @State private var showGoalEditor = false
    @State private var goalDraft = ""
    @State private var showFishingSelector = false
    @State private var showRoastSelector = false

    var body: some View {
        KintTanyDashboardView(
            state: $dashboard,
            sizingMode: .aspectFit,
            actions: dashboardActions,
            referenceOverlayOpacity: 0
        ) {
            avatarView
        }
        .onAppear { syncFromApp() }
        .onReceive(app.objectWillChange) { _ in
            DispatchQueue.main.async { syncFromApp() }
        }
        .alert("Meta da sessão", isPresented: $showGoalEditor) {
            TextField("Meta", text: $goalDraft)
                .keyboardType(.numberPad)
            Button("Cancelar", role: .cancel) {}
            Button("Salvar") { commitGoal() }
        } message: {
            Text("Defina qualquer meta entre 1 e 100000. A alteração fica bloqueada durante uma atividade ativa.")
        }
        .confirmationDialog("O que assar", isPresented: $showRoastSelector, titleVisibility: .visible) {
            ForEach(RoastPitMode.allCases) { roast in Button(roast.label) { app.selectedRoastMode = roast; start(.roastPit) } }
            Button("Cancelar", role: .cancel) {}
        } message: { Text("Cada unidade consome 1 Wood; o resultado é confirmado pelo servidor.") }
        .confirmationDialog("Isca da pesca", isPresented: $showFishingSelector, titleVisibility: .visible) {
            baitButton(.feather)
            baitButton(.trout)
            baitButton(.bass)
            baitButton(.tuna)
            baitButton(.squid)
            Button("Cancelar", role: .cancel) {}
        } message: {
            Text("Feather e Trout usam protocolos validados; as demais continuam bloqueadas pela engine até serem validadas.")
        }
    }

    @ViewBuilder
    private var avatarView: some View {
        if app.hasSession {
            CharacterVoxel3DView(appearance: app.characterProfile.appearance)
                .scaleEffect(1.42)
                .padding(-20)
                .accessibilityLabel("Personagem da conta conectada")
        } else {
            Image(systemName: "person.crop.square")
                .resizable()
                .scaledToFit()
                .padding(18)
                .foregroundStyle(KintTanyTheme.mutedInk)
                .accessibilityLabel("Sem sessão conectada")
        }
    }

    private var dashboardActions: KintTanyDashboardActions {
        KintTanyDashboardActions(
            selectActivity: { activity in
                guard app.activity == nil else { return }
                switch activity {
                case .idle: break
                case .wood: start(.tree)
                case .coal: start(.coal)
                case .stone: start(.stone)
                case .ironOre: start(.iron)
                case .silverOre: start(.silver)
                case .cacti: start(.cacti)
                case .fishing: showFishingSelector = true
                case .roastPit: showRoastSelector = true
                case .chicken: start(.chicken)
                case .zombie: start(.zombie)
                case .dragon: start(.dragon)
                }
            },
            togglePause: {
                // The merged main4/main5 engine has a safety-aware STOP but no
                // pausable execution primitive. Keep the exact kit control and
                // route it to the existing safe-stop path rather than inventing
                // a second execution state outside the authoritative engine.
                if app.activity != nil { app.stop() }
            },
            selectTab: { tab in
                dashboard.selectedTab = tab
                switch tab {
                case .stats:
                    showCharacterStats = true
                case .quests:
                    showDailyQuests = true
                case .session:
                    showLogin = true
                }
            },
            openFullLog: { showFullLog = true },
            editTarget: {
                guard app.activity == nil else { return }
                goalDraft = String(app.goal)
                showGoalEditor = true
            },
            decrementTarget: { adjustGoal(by: -10) },
            incrementTarget: { adjustGoal(by: 10) }
        )
    }

    @ViewBuilder
    private func baitButton(_ bait: FishingBait) -> some View {
        Button(bait.displayName + (bait.isAutomationValidated ? "" : " • não validado")) {
            app.selectedFishingBait = bait
            start(.fishing)
        }
    }

    private func adjustGoal(by delta: Int) {
        guard app.activity == nil else { return }
        app.goal = min(100_000, max(1, app.goal + delta))
        syncFromApp()
    }

    private func commitGoal() {
        guard app.activity == nil else { return }
        let parsed = Int(goalDraft.trimmingCharacters(in: .whitespacesAndNewlines)) ?? app.goal
        app.goal = min(100_000, max(1, parsed))
        syncFromApp()
    }

    private func start(_ mode: ActivityMode) {
        guard app.activity == nil else { return }
        dashboard.selectedActivity = kintActivity(for: mode)
        dashboard.activityTitle = mode.localizedTitle
        app.start(mode)
        syncFromApp()
    }

    private func syncFromApp() {
        let currentMode = app.activity
        let selected = currentMode.map(kintActivity(for:)) ?? .idle
        let target = currentMode == nil ? app.goal : app.sessionGoal
        let combat = currentMode == .chicken || currentMode == .zombie || currentMode == .dragon
        let actionProgress = combat ? app.stats.confirmedHits : app.stats.successes
        let actionRequirement = combat
            ? max(1, max(app.stats.hits, app.stats.confirmedHits))
            : max(1, target)
        let skillStats = app.characterProfile.skills
        let lastEvent = app.stats.lastEvent.isEmpty ? (app.currentTarget ?? "—") : app.stats.lastEvent
        let regionRaw = app.world.serverRegion ?? app.world.region
        let region = regionRaw
            .replacingOccurrences(of: "_", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .capitalized
        let rate = currentMode == nil ? "0.00/min" : app.formattedRatePerMinute()
        let status = currentMode == nil ? app.state.label : app.displayStatusMessage

        dashboard = KintTanyDashboardState(
            isOnline: app.connected,
            selectedActivity: selected,
            activityTitle: currentMode?.localizedTitle ?? "Aguardando atividade",
            completed: currentMode == nil ? 0 : app.stats.successes,
            target: target,
            actionProgress: actionProgress,
            actionRequirement: actionRequirement,
            rateText: rate,
            statusText: status,
            skills: [
                .init(name: "Combat", value: skillStats.level(for: .combat)),
                .init(name: "Wood", value: skillStats.level(for: .woodcutting)),
                .init(name: "Mining", value: skillStats.level(for: .mining)),
                .init(name: "Fishing", value: skillStats.level(for: .fishing)),
                .init(name: "Cooking", value: skillStats.level(for: .cooking)),
                .init(name: "Smithing", value: skillStats.level(for: .smithing)),
            ],
            totalLevel: app.characterProfile.totalLevel,
            totalLevelMaximum: CharacterSkillStats.maxLevel,
            location: .init(
                region: region.isEmpty ? "—" : region,
                position: String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z),
                resources: app.resourceCount,
                mobs: app.mobCount,
                lastEvent: lastEvent
            ),
            session: .init(
                target: target,
                successes: app.stats.successes,
                failures: app.stats.failures,
                attempts: app.stats.attempts
            ),
            isRunning: currentMode != nil,
            isPaused: false,
            selectedTab: dashboard.selectedTab
        )
    }

    private func kintActivity(for mode: ActivityMode) -> KintActivity {
        switch mode {
        case .tree: .wood
        case .coal: .coal
        case .stone: .stone
        case .iron: .ironOre
        case .silver: .silverOre
        case .cacti: .cacti
        case .fishing: .fishing
        case .roastPit: .roastPit
        case .chicken: .chicken
        case .zombie: .zombie
        case .dragon: .dragon
        }
    }
}