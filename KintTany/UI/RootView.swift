import Foundation
import SwiftUI
import UIKit
import WebKit
import SceneKit

struct RootView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var showLogin=false
    @State private var showFullLog=false
    @State private var showCharacterStats=false
    @State private var showDailyQuests=false
    @FocusState private var goalFieldFocused: Bool
    private let ink=Color(red:0.16,green:0.15,blue:0.14)
    private let copper=Color(red:0.67,green:0.34,blue:0.23)
    private let paper=Color(red:0.925,green:0.91,blue:0.875)

    var body: some View {
        ZStack {
            PaperTexture()
            GeometryReader { g in
                let W:CGFloat=390, H:CGFloat=800
                let s=min(g.size.width/W,g.size.height/H)
                VStack(spacing:0) {
                    header.frame(height:50)
                    hero.frame(height:280)
                    Divider().overlay(ink.opacity(0.35))
                    stats.frame(height:202)
                    Divider().overlay(ink.opacity(0.35))
                    metrics.frame(height:58)
                    stop.frame(height:66)
                    nav.frame(height:52)
                    log.frame(height:46)
                }
                .padding(.horizontal,10).frame(width:W,height:H,alignment:.top)
                .scaleEffect(s,anchor:.top).frame(width:g.size.width,height:g.size.height,alignment:.top)
            }
        }
        .preferredColorScheme(.light)
        .sheet(isPresented:$showLogin){LoginWebView(onCookie:{app.saveCookie($0);showLogin=false},onDiagnostic:{app.diagnostic($0)}).preferredColorScheme(.dark)}
        .sheet(isPresented:$showFullLog){FullLogView().environmentObject(app).preferredColorScheme(.dark)}
        .sheet(isPresented:$showCharacterStats){CharacterStatsView().environmentObject(app).preferredColorScheme(.dark)}
        .sheet(isPresented:$showDailyQuests){DailyQuestsView().environmentObject(app).preferredColorScheme(.dark)}
        .toolbar{ToolbarItemGroup(placement:.keyboard){Spacer();Button("OK"){app.goal=min(100000,max(1,app.goal));goalFieldFocused=false}}}
        .onChange(of:scenePhase){_,p in app.handleScenePhase(p)}
        .task{await app.refreshCharacterProfile()}
    }

    private var header: some View {
        ZStack {
            Text("KintTany").font(.system(size:28,weight:.regular,design:.rounded))
            HStack(spacing:7){Circle().fill(app.connected ? Color(red:0.42,green:0.54,blue:0.39):Color(red:0.70,green:0.55,blue:0.31)).frame(width:14,height:14).overlay(Circle().stroke(ink.opacity(0.35)));Text(app.connected ? "ONLINE":"PRONTO").font(.system(size:15,weight:.regular));Spacer()}
        }.foregroundStyle(ink).padding(.horizontal,8)
    }

    private var hero: some View {
        HStack(spacing:12) {
            ZStack {
                if app.hasSession { CharacterVoxel3DView(appearance:app.characterProfile.appearance).scaleEffect(1.56).padding(-28) }
                else { Image(systemName:"person.crop.square").font(.system(size:48)).foregroundStyle(ink.opacity(0.5)) }
            }
            .frame(width:108).contentShape(Rectangle()).onTapGesture{app.hasSession ? (showCharacterStats=true):(showLogin=true)}
            .embossedPanel(cornerRadius:16,fill:paper)
            VStack(spacing:4) {
                HStack{Text(app.activity?.localizedTitle ?? "Selecione");Spacer();Text("\(app.stats.successes)/\(app.activity == nil ? app.goal:app.sessionGoal)")}
                    .font(.system(size:20,weight:.regular,design:.rounded))
                beads
                HStack{Text("Progresso \(app.stats.successes)/\(app.activity == nil ? app.goal:app.sessionGoal)");Spacer();Text(app.activity == nil ? "Aguardando resultado":app.state.label)}
                    .font(.system(size:11.5)).lineLimit(1)
                activities
            }.foregroundStyle(ink)
        }.padding(.vertical,4)
    }

    private var beads: some View {
        HStack(spacing:5){ForEach(0..<12,id:\.self){i in Circle().fill(i < max(0,min(12,Int(ceil(app.progress*12)))) ? copper:Color(red:0.83,green:0.81,blue:0.76)).frame(width:17,height:17).overlay(Circle().stroke(ink.opacity(0.16)))}}.padding(5).background(Capsule().fill(Color(red:0.87,green:0.85,blue:0.80)).shadow(color:.black.opacity(0.15),radius:2,x:1,y:1))
    }

    private var activities: some View {
        let cols=Array(repeating:GridItem(.flexible(),spacing:2),count:5)
        return LazyVGrid(columns:cols,spacing:3){ForEach(ActivityMode.allCases){m in tile(m)}}.frame(maxHeight:.infinity)
    }
    @ViewBuilder private func tile(_ m:ActivityMode)->some View {
        if m == .fishing {
            Menu { ForEach(FishingBait.allCases){b in Button{app.selectedFishingBait=b;app.start(.fishing)}label:{Text((app.selectedFishingBait==b ? "✓ ":"")+b.displayName)}} }
            label:{tileLabel(m)}.buttonStyle(.plain).disabled(app.activity != nil)
        } else { Button{guard app.activity==nil else{return};app.start(m)}label:{tileLabel(m)}.buttonStyle(.plain).disabled(app.activity != nil) }
    }
    private func tileLabel(_ m:ActivityMode)->some View {
        VStack(spacing:1){Image(sprite(m)).resizable().scaledToFit().frame(width:46,height:46);Text(m.localizedTitle).font(.system(size:11.5)).lineLimit(1).minimumScaleFactor(0.7);if m == .fishing {Text(bait).font(.system(size:8)).foregroundStyle(ink.opacity(0.55))}}
        .foregroundStyle(ink).frame(maxWidth:.infinity,minHeight:66).opacity(app.activity==nil ? 1:0.45)
    }
    private var bait:String {switch app.selectedFishingBait{case .feather:"Feather";case .trout:"Trout";case .bass:"Bass";case .tuna:"Tuna";case .squid:"Squid"}}
    private func sprite(_ m:ActivityMode)->String {switch m{case .tree:"CloneWood";case .coal:"CloneCoal";case .stone:"CloneStone";case .iron:"CloneIron";case .silver:"CloneSilver";case .cacti:"CloneCacti";case .fishing:"CloneFishing";case .chicken:"CloneChicken";case .zombie:"CloneZombie";case .dragon:"CloneDragon"}}

    private var stats: some View {
        VStack(alignment:.leading,spacing:3) {
            Text("STATS").font(.system(size:20,weight:.regular))
            HStack(spacing:8) {
                VStack(spacing:3){ForEach(CharacterSkill.allCases){skill in skillRow(skill)};Divider();HStack(spacing:6){Text("Total Level").frame(width:68,alignment:.leading);bar(Double(app.characterProfile.totalLevel)/40);Text("\(app.characterProfile.totalLevel)").frame(width:28,alignment:.trailing)}.font(.system(size:12.5))}
                Rectangle().fill(ink.opacity(0.25)).frame(width:1)
                VStack(alignment:.leading,spacing:5){Image(systemName:"mountain0.2.fill").font(.system(size:30)).foregroundStyle(Color(red:0.39,green:0.43,blue:0.34)).frame(maxWidth:.infinity);line("Região",app.world.serverRegion ?? app.player.region);line("Posição",String(format:"%0.1f, %0.1f",app.player.position.x,app.player.position.z));line("Recursos","\(app.resourceCount)");line("Mobs","\(app.mobCount)");Text("Último evento").font(.system(size:11.5));Text(app.stats.lastEvent.isEmpty ? "—":app.stats.lastEvent).font(.system(size:10.5)).lineLimit(1)}
                    .frame(width:112)
            }
        }.foregroundStyle(ink).padding(.horizontal,6).padding(.vertical,5)
    }
    private func skillRow(_ s:CharacterSkill)->some View {let l=app.characterProfile.skills.level(for:s);return HStack(spacing:6){Text(skillName(s)).frame(width:72,alignment:.leading);bar(Double(l)/40);Text("\(l)/40").frame(width:34,alignment:.trailing)}.font(.system(size:12))}
    private func skillName(_ s:CharacterSkill)->String{switch s{case .combat:"Combat";case .woodcutting:"Wood";case .mining:"Mining";case .fishing:"Fishing";case .cooking:"Cooking";case .smithing:"Smithing"}}
    private func bar(_ p:Double)->some View {GeometryReader{g in ZStack(alignment:.leading){Capsule().fill(Color(red:0.83,green:0.81,blue:0.76));Capsule().fill(copper).frame(width:max(6,g.size.width*min(1,max(0,p))))}}.frame(height:11)}
    private func line(_ a:String,_ b:String)->some View {HStack(spacing:3){Text(a);Text(b).lineLimit(1).minimumScaleFactor(0.7)}.font(.system(size:11))}

    private var metrics:some View {HStack(spacing:0){metric("Meta da sessão",app.activity==nil ? "\(app.goal)":"\(app.sessionGoal)");div;metric("Sucessos","\(app.stats.successes)");div;metric("Falhas","\(app.stats.failures)");div;metric("Tentativas","\(app.stats.attempts)")}.padding(.vertical,6)}
    private var div:some View{Rectangle().fill(ink.opacity(0.25)).frame(width:1,height:44)}
    private func metric(_ t:String,_ v:String)->some View{VStack(spacing:2){Text(t).font(.system(size:10.5));Text(v).font(.system(size:22))}.frame(maxWidth:.infinity).foregroundStyle(ink)}
    private var stop:some View{Button{if app.activity != nil{app.stop()}}label:{HStack(spacing:18){Image(systemName:"stop.fill");Text(app.activity==nil ? "PRONTO":"PARAR")}.font(.system(size:22,weight:.regular)).foregroundStyle(Color(red:0.92,green:0.88,blue:0.82)).frame(maxWidth:.infinity,height:56).background(RoundedRectangle(cornerRadius:16).fill(app.activity==nil ? copper.opacity(0.35):copper)).overlay(RoundedRectangle(cornerRadius:16).stroke(ink.opacity(0.55)))}.buttonStyle(.plain).disabled(app.activity==nil)}
    private var nav:some View{HStack(spacing:0){navB("STATS","chart.bar.fill"){showCharacterStats=true};divN;navB("QUESTS","list.bullet.rectangle"){showDailyQuests=true};divN;navB("SESSÃO","slider.horizontal0.3"){showLogin=true}}.overlay(alignment:.top){Rectangle().fill(ink.opacity(0.3)).frame(height:1)}.overlay(alignment:.bottom){Rectangle().fill(ink.opacity(0.3)).frame(height:1)}}
    private var divN:some View{Rectangle().fill(ink.opacity(0.25)).frame(width:1,height:30)}
    private func navB(_ t:String,_ i:String,_ a:@escaping()->Void)->some View{Button(action:a){HStack(spacing:8){Image(systemName:i).font(.system(size:20));Text(t).font(.system(size:13))}.foregroundStyle(ink).frame(maxWidth:.infinity,maxHeight:.infinity)}.buttonStyle(.plain)}
    private var log:some View{Button{showFullLog=true}label:{HStack{Image(systemName:"doc.text");Text("Log completo");Spacer();Image(systemName:"chevron.right")}.font(.system(size:14)).foregroundStyle(ink).padding(.horizontal,14)}.buttonStyle(.plain)}

}
private struct PaperTexture:View{var body:some View{ZStack{Color(red:0.925,green:0.91,blue:0.875);Canvas{c,s in for i in 0..<280{let x=CGFloat((i*73)%997)/997*s.width,y=CGFloat((i*149)%991)/991*s.height;c.fill(Path(ellipseIn:CGRect(x:x,y:y,width:0.7,height:0.7)),with:.color(.black.opacity(0.025)))}}}.ignoresSafeArea()}}
private struct EmbossedPanelModifier:ViewModifier{let cornerRadius:CGFloat;let fill:Color;func body(content:Content)->some View{content.background(RoundedRectangle(cornerRadius:cornerRadius).fill(fill).shadow(color:.white.opacity(0.8),radius:2,x:-2,y:-2).shadow(color:.black.opacity(0.17),radius:3,x:2,y:2)).overlay(RoundedRectangle(cornerRadius:cornerRadius).stroke(Color.black.opacity(0.12),lineWidth:1))}}
private extension View{func embossedPanel(cornerRadius:CGFloat,fill:Color)->some View{modifier(EmbossedPanelModifier(cornerRadius:cornerRadius,fill:fill))}}

private struct DailyQuestsView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.dismiss) private var dismiss

    private let paper = Color(red: 0.91, green: 0.895, blue: 0.855)
    private let ink = Color(red: 0.16, green: 0.15, blue: 0.14)
    private let copper = Color(red: 0.67, green: 0.34, blue: 0.23)

    var body: some View {
        ZStack {
            PaperTexture()
            GeometryReader { proxy in
                let designWidth: CGFloat = 430
                let designHeight: CGFloat = 860
                let scale = min(proxy.size.width / designWidth, proxy.size.height / designHeight)

                VStack(spacing: 12) {
                    HStack {
                        Button("Fechar") { dismiss() }
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundStyle(ink)
                        Spacer()
                        Text("QUESTS")
                            .font(.system(size: 23, weight: .bold, design: .rounded))
                            .foregroundStyle(ink)
                        Spacer()
                        Button {
                            Task { await app.refreshDailyQuests() }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundStyle(ink)
                        }
                    }
                    .padding(.horizontal, 6)
                    .frame(height: 42)

                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("DAILY QUESTS")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                            Text("Dados oficiais do Kintara")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(ink.opacity(0.58))
                        }
                        Spacer()
                        if app.dailyQuestsLoading { ProgressView().tint(copper) }
                    }
                    .foregroundStyle(ink)
                    .padding(.horizontal, 4)

                    if let error = app.dailyQuestsError {
                        Text(error)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(copper)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    ForEach(app.dailyQuests.prefix(3)) { quest in
                        questCard(quest)
                    }

                    if !app.dailyQuestsLoading && app.dailyQuests.isEmpty && app.dailyQuestsError == nil {
                        Text("Nenhuma Daily Quest publicada pelo servidor.")
                            .font(.system(size: 12.5, weight: .regular, design: .rounded))
                            .foregroundStyle(ink.opacity(0.62))
                            .frame(maxWidth: .infinity)
                            .padding(24)
                            .embossedPanel(cornerRadius: 18, fill: paper)
                    }

                    Spacer(minLength: 2)

                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("RESET")
                                .font(.system(size: 11, weight: .bold, design: .rounded))
                                .foregroundStyle(ink.opacity(0.55))
                            Text("00:00 UTC")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                                .foregroundStyle(ink)
                        }
                        Spacer()
                        if let day = app.dailyQuestDay {
                            Text(day)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(ink.opacity(0.58))
                        }
                    }
                    .padding(14)
                    .embossedPanel(cornerRadius: 16, fill: paper)
                }
                .padding(16)
                .frame(width: designWidth, height: designHeight, alignment: .top)
                .scaleEffect(scale, anchor: .top)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }
        }
        .preferredColorScheme(.light)
        .task { await app.refreshDailyQuests() }
    }

    private func questCard(_ quest: DailyQuest) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(quest.label)
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundStyle(ink)
                    .lineLimit(1)
                Spacer()
                Text(quest.claimed ? "RESGATADA" : (quest.isComplete ? "CONCLUÍDA" : "ATIVA"))
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(copper)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color(red: 0.82, green: 0.80, blue: 0.75))
                    Capsule().fill(copper)
                        .frame(width: max(0, geo.size.width * quest.progressFraction))
                }
            }
            .frame(height: 8)

            HStack {
                Text("\(quest.progress) / \(quest.target)")
                    .font(.system(size: 16, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                Spacer()
                Text(quest.kind)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(ink.opacity(0.5))
            }
            .foregroundStyle(ink)

            Label(quest.rewardSummary, systemImage: "sparkles")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(copper)
                .lineLimit(1)
        }
        .padding(14)
        .embossedPanel(cornerRadius: 18, fill: paper)
    }
}

private struct CharacterVoxel3DView: UIViewRepresentable {
    let appearance: CharacterAppearance

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject {
        weak var view: SCNView?
        private var lastX: CGFloat = 0
        @objc func pan(_ gesture: UIPanGestureRecognizer) {
            guard let avatar = view?.scene?.rootNode.childNode(withName: "avatar", recursively: false) else { return }
            let x = gesture.translation(in: view).x
            if gesture.state == .began { lastX = x; return }
            let dx = x - lastX; lastX = x
            avatar.eulerAngles.y += Float(dx) * 0.012
        }
    }

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView()
        view.backgroundColor = .clear
        view.isOpaque = false
        view.autoenablesDefaultLighting = false
        view.allowsCameraControl = false
        view.antialiasingMode = .multisampling4X
        let pan = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.pan(_:)))
        view.addGestureRecognizer(pan)
        context.coordinator.view = view
        view.scene = Self.scene(for: appearance)
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) {
        let yaw = view.scene?.rootNode.childNode(withName: "avatar", recursively: false)?.eulerAngles.y ?? 0
        view.scene = Self.scene(for: appearance)
        view.scene?.rootNode.childNode(withName: "avatar", recursively: false)?.eulerAngles.y = yaw
    }

    private static func scene(for a: CharacterAppearance) -> SCNScene {
        let scene = SCNScene()
        let root = SCNNode()
        root.name = "avatar"
        scene.rootNode.addChildNode(root)

        // Port nativo do rig real buildCharacter/applyOutfit do Kintara.
        let S: CGFloat = 2.0
        let yOffset: Float = 0.45
        let outlineExp: CGFloat = 0.018
        func sc(_ v: CGFloat) -> CGFloat { v * S }
        func mat(_ color: UIColor, constant: Bool = false, image: UIImage? = nil) -> SCNMaterial {
            let m = SCNMaterial()
            m.diffuse.contents = image ?? color
            m.ambient.contents = image ?? color
            m.lightingModel = constant ? .constant : .lambert
            m.isDoubleSided = false
            m.diffuse.magnificationFilter = .nearest
            m.diffuse.minificationFilter = .nearest
            return m
        }
        func outlineMat() -> SCNMaterial {
            let m = SCNMaterial()
            m.diffuse.contents = UIColor.black
            m.ambient.contents = UIColor.black
            m.lightingModel = .constant
            m.cullMode = .front
            return m
        }
        @discardableResult
        func part(_ w: CGFloat, _ h: CGFloat, _ d: CGFloat,
                  _ x: CGFloat, _ y: CGFloat, _ z: CGFloat,
                  _ material: SCNMaterial, parent: SCNNode = root,
                  local: Bool = false, outlined: Bool = true) -> SCNNode {
            let g = SCNBox(width: sc(w), height: sc(h), length: sc(d), chamferRadius: 0)
            g.materials = [material]
            let n = SCNNode(geometry: g)
            n.position = SCNVector3(Float(sc(x)), Float(sc(y)) + (local ? 0 : yOffset), Float(sc(z)))
            n.renderingOrder = 1
            parent.addChildNode(n)
            if outlined {
                let og = SCNBox(width: sc(w + outlineExp * 2),
                                height: sc(h + outlineExp * 2),
                                length: sc(d + outlineExp * 2),
                                chamferRadius: 0)
                og.materials = [outlineMat()]
                let o = SCNNode(geometry: og)
                o.renderingOrder = 0
                n.addChildNode(o)
            }
            return n
        }

        let skinHex = [15853791, 14926238, 13935988, 8281929, 6046514]
        let skin = Self.kintaraColor(skinHex[max(0, min(skinHex.count - 1, a.skinTone))])
        let skinMat = mat(skin)
        let eyeMat = mat(Self.kintaraColor(0x20120F), constant: true)
        let hatMat = mat(Self.kintaraColor(a.hatColor ?? 3816778))
        let topMat = mat(Self.kintaraColor(a.topColor ?? 2450411))
        let pantsMat = mat(Self.kintaraColor(a.pantsColor ?? 2450411))
        let strapMat = mat(Self.kintaraColor(a.strapColor ?? 1790656))
        let shoeMat = mat(Self.kintaraColor(a.shoeColor ?? 16777215))

        // Exact pc_head + eyes from Kintara uHt/buildCharacter.
        part(0.44,0.34,0.44,0,0.88,0,skinMat)

        // pc_eyeL / pc_eyeR are face pixels, not volumetric blocks.
        // Keep them flush with the head so rotation never exposes black side faces.
        func eye(_ x: CGFloat) {
            let plane = SCNPlane(width: sc(0.07), height: sc(0.13))
            plane.materials = [eyeMat]
            let node = SCNNode(geometry: plane)
            node.name = x < 0 ? "pc_eyeL" : "pc_eyeR"
            node.position = SCNVector3(Float(sc(x)), Float(sc(0.90)) + yOffset, Float(sc(0.221)))
            node.renderingOrder = 6
            root.addChildNode(node)
        }
        eye(-0.09)
        eye(0.09)

        // Exact oUe top geometry table used by applyOutfitToGroup.
        let tops: [(CGFloat,CGFloat,CGFloat,CGFloat,Bool,Bool,CGFloat,CGFloat,CGFloat,CGFloat,CGFloat,Bool,Bool)] = [
            (0.300,0.280,0.170,0.500,false,false,0.720,0.260,0.110,0.170,0.510,false,false),
            (0.348,0.368,0.212,0.518,true, false,0.718,0.260,0.110,0.170,0.505,false,false),
            (0.340,0.340,0.200,0.508,false,false,0.705,0.260,0.110,0.170,0.508,false,true),
            (0.360,0.385,0.215,0.525,false,false,0.715,0.305,0.112,0.172,0.498,true, false),
            (0.375,0.368,0.228,0.518,false,true, 0.748,0.325,0.118,0.176,0.488,true, false)
        ]
        let ti = max(0, min(4, a.top))
        let T = tops[ti]
        let isSeason = (a.topFX == "season1" || a.topFX == "season1gold") && ti == 2
        let seasonImage = isSeason ? Self.kintaraSeasonOneTee(gold: a.topFX == "season1gold") : nil
        let torsoMat = isSeason ? mat(.white, constant: true, image: seasonImage) : (ti == 0 ? skinMat : topMat)
        let torso = part(T0.0,T0.1,T0.2,0,T0.3,0,torsoMat)

        let armMat = T0.11 && ti > 0 ? torsoMat : skinMat
        let armL = part(T0.8,T0.7,T0.9,-0.225,T0.10,0,armMat)
        let armR = part(T0.8,T0.7,T0.9, 0.225,T0.10,0,armMat)
        if T0.12 {
            part(0.138,0.136,0.206,0,0.066,0.004,torsoMat,parent:armL,local:true)
            part(0.138,0.136,0.206,0,0.066,0.004,torsoMat,parent:armR,local:true)
        }
        if T0.4 {
            part(0.05,0.20,0.06,-0.09,T0.6,0.08,strapMat)
            part(0.05,0.20,0.06, 0.09,T0.6,0.08,strapMat)
        }
        if T0.5 {
            part(T0.0 + 0.05,0.21,0.27,0,T0.3 + 0.20,-0.13,torsoMat)
        }

        // Exact rUe pants geometry table.
        let pants: [(CGFloat,CGFloat,CGFloat,CGFloat,Bool,Bool)] = [
            (0.140,0.300,0.170,0.09,false,false),
            (0.140,0.300,0.170,0.09,false,false),
            (0.175,0.300,0.215,0.09,false,false),
            (0.150,0.130,0.200,0.09,true, false),
            (0.140,0.300,0.170,0.09,false,true)
        ]
        let pi = max(0, min(4, a.pants))
        let P = pants[pi]
        let legY = CGFloat(0.36) - P0.1 * 0.5
        let legMat = pi == 0 ? skinMat : pantsMat
        let legL = part(P0.0,P0.1,P0.2,-P0.3,legY,0,legMat)
        let legR = part(P0.0,P0.1,P0.2, P0.3,legY,0,legMat)

        var legSkinH: CGFloat = 0.195
        if P0.4 {
            let g = legY - P0.1 * 0.5
            legSkinH = max(0.12, g - 0.008 - 0.06)
            let localY = -P0.1 * 0.5 - 0.008 - legSkinH * 0.5
            part(0.11,legSkinH,0.165,0,localY,0,skinMat,parent:legL,local:true)
            part(0.11,legSkinH,0.165,0,localY,0,skinMat,parent:legR,local:true)
        }
        if P0.5 {
            func cargo(_ x: CGFloat) {
                let holder = SCNNode()
                holder.position = SCNVector3(Float(sc(x)),Float(sc(legY + 0.04)) + yOffset,Float(sc(0.102)))
                root.addChildNode(holder)
                part(0.065,0.110,0.032,0,0,0,pantsMat,parent:holder,local:true)
                part(0.070,0.022,0.036,0,0.055,0.012,pantsMat,parent:holder,local:true)
                part(0.050,0.030,0.015,0,-0.010,0.019,pantsMat,parent:holder,local:true)
            }
            cargo(-P0.3 - 0.072); cargo(P0.3 + 0.072)
        }

        // Exact Nue shoe geometry + UZe anchor formula.
        if a.shoe > 0 {
            let shoes: [(CGFloat,CGFloat,CGFloat,CGFloat)] = [(0.182,0.058,0.234,0.028),(0.178,0.048,0.228,0.030)]
            let sh = shoes[min(shoes.count - 1, a.shoe - 1)]
            let anchor = (P0.4 ? -P0.1*0.5 - 0.008 - legSkinH + sh0.1*0.5 + 0.015
                              : -P0.1*0.5 + sh0.1*0.5 + 0.015) - 0.018
            let z = sh0.3 - 0.006
            part(sh0.0,sh0.1,sh0.2,-0.012,anchor,z,shoeMat,parent:legL,local:true)
            part(sh0.0,sh0.1,sh0.2, 0.012,anchor,z,shoeMat,parent:legR,local:true)
        }

        // Exact base hat assets captured from pc_hatHolder.
        if a.hat > 0 && a.hat <= 9 {
            let holder = SCNNode()
            holder.position = SCNVector3(0,Float(sc(1.12)) + yOffset,0)
            root.addChildNode(holder)
            func hp(_ w: CGFloat,_ h: CGFloat,_ d: CGFloat,_ x: CGFloat,_ y: CGFloat,_ z: CGFloat,
                    rx: Float = 0, rz: Float = 0) {
                let n = part(w,h,d,x,y,z,hatMat,parent:holder,local:true)
                n.eulerAngles.x = rx; n.eulerAngles.z = rz
            }
            switch a.hat {
            case 1:
                hp(0.42,0.11,0.44,0,0.045,0); hp(0.42,0.024,0.484,0,-0.01,0.122)
            case 2:
                hp(0.64,0.025,0.64,0,-0.03,0); hp(0.28,0.085,0.28,0,0.045,0)
            case 3:
                hp(0.56,0.022,0.50,0,-0.03,0); hp(0.36,0.14,0.34,0,0.065,0)
                hp(0.065,0.03,0.52,-0.28,-0.018,0,rz:-0.58); hp(0.065,0.03,0.52,0.28,-0.018,0,rz:0.58)
                hp(0.44,0.028,0.095,0,-0.008,0.285,rx:-0.62); hp(0.44,0.028,0.095,0,-0.008,-0.285,rx:0.62)
            case 4:
                hp(0.10,0.22,0.38,0,0.04,0); hp(0.045,0.10,0.14,-0.07,-0.02,0.02); hp(0.045,0.10,0.14,0.07,-0.02,0.02)
            case 5:
                let sphere = SCNSphere(radius: sc(0.27)); sphere.segmentCount = 18; sphere.materials = [hatMat]
                let n = SCNNode(geometry:sphere)
                n.scale = SCNVector3(1.38,0.50,1.36)
                n.position = SCNVector3(0,Float(sc(-0.07 + CGFloat(Darwin.cos(0.11)) * 0.135)),0)
                n.eulerAngles = SCNVector3(0.11,0,0.05)
                holder.addChildNode(n)
            case 6:
                hp(0.41,0.052,0.39,0,-0.042,0)
            case 7:
                hp(0.42,0.11,0.44,0,0.045,0); hp(0.42,0.024,0.484,0,-0.01,-0.122)
            case 8:
                hp(0.50,0.045,0.48,0,-0.06,0); hp(0.34,0.16,0.34,0,0.02,0)
            case 9:
                hp(0.50,0.045,0.48,0,-0.06,0); hp(0.34,0.28,0.34,0,0.1025,0)
            default: break
            }
        }

        // Exact Season 1 chest overlay: 0.32 plane at torso depth*0.5*1.04 + 0.012.
        if isSeason {
            let plane = SCNPlane(width: sc(0.32), height: sc(0.32))
            let em = SCNMaterial()
            let image = Self.kintaraSeasonOneEmblem(gold: a.topFX == "season1gold")
            em.diffuse.contents = image; em.ambient.contents = image
            em.lightingModel = .constant; em.isDoubleSided = true
            plane.materials = [em]
            let badge = SCNNode(geometry:plane)
            badge.position = SCNVector3(0,Float(sc(T0.3 + 0.04)) + yOffset,Float(sc(T0.2*0.5*1.04 + 0.012)))
            badge.renderingOrder = 5
            root.addChildNode(badge)
            torso.renderingOrder = 4
        }

        let ambient = SCNLight(); ambient.type = .ambient; ambient.intensity = 780
        ambient.color = UIColor(white:0.94,alpha:1)
        let ambientNode = SCNNode(); ambientNode.light = ambient; scene.rootNode.addChildNode(ambientNode)
        let key = SCNLight(); key.type = .directional; key.intensity = 420; key.color = UIColor.white
        let keyNode = SCNNode(); keyNode.light = key; keyNode.eulerAngles = SCNVector3(-0.55,-0.65,0)
        scene.rootNode.addChildNode(keyNode)

        let camera = SCNCamera()
        camera.usesOrthographicProjection = true; camera.orthographicScale = 3.95
        camera.zNear = 0.1; camera.zFar = 100
        let cameraNode = SCNNode(); cameraNode.camera = camera
        cameraNode.position = SCNVector3(0,2.02,7.0)
        cameraNode.look(at: SCNVector3(0,1.88,0))
        scene.rootNode.addChildNode(cameraNode)
        return scene
    }

    private static func kintaraColor(_ value: Int) -> UIColor {
        UIColor(red:CGFloat((value >> 16) & 255)/255,
                green:CGFloat((value >> 8) & 255)/255,
                blue:CGFloat(value & 255)/255,alpha:1)
    }

    private static func kintaraSeasonOneTee(gold: Bool) -> UIImage {
        UIGraphicsImageRenderer(size:CGSize(width:64,height:256)).image { r in
            let c = r.cgContext
            let colors = gold
                ? [kintaraColor(0xF2E3B3).cgColor,kintaraColor(0xD9A83C).cgColor,kintaraColor(0xA87A22).cgColor]
                : [kintaraColor(0x3D2A7D).cgColor,kintaraColor(0x2C1C5E).cgColor,kintaraColor(0x241546).cgColor]
            let locs:[CGFloat] = gold ? [0,0.45,1] : [0,0.55,1]
            let g = CGGradient(colorsSpace:CGColorSpaceCreateDeviceRGB(),colors:colors as CFArray,locations:locs)!
            c.drawLinearGradient(g,start:.zero,end:CGPoint(x:0,y:256),options:[])
            c.setFillColor((gold ? kintaraColor(0x3D2A7D) : kintaraColor(0xD9A83C)).cgColor)
            c.fill(CGRect(x:0,y:244,width:64,height:6))
        }
    }

    private static func kintaraSeasonOneEmblem(gold: Bool) -> UIImage {
        UIGraphicsImageRenderer(size:CGSize(width:256,height:256)).image { r in
            let c = r.cgContext
            c.clear(CGRect(x:0,y:0,width:256,height:256))
            c.saveGState(); c.translateBy(x:128,y:116); c.scaleBy(x:1.6,y:1.6)
            let main = gold ? kintaraColor(0x3D2A7D) : kintaraColor(0xD9A83C)
            let glyph = gold ? kintaraColor(0x241546) : kintaraColor(0xF2E3B3)
            c.setStrokeColor(main.cgColor); c.setFillColor(main.cgColor)
            c.setLineWidth(13); c.setLineCap(.round)
            for side in [-1.0,1.0] {
                let start = side == -1 ? Double.pi*0.56 : -Double.pi*0.04
                let finish = side == -1 ? Double.pi*1.04 : Double.pi*0.44
                c.addArc(center:CGPoint(x:0,y:10),radius:58,startAngle:CGFloat(start),endAngle:CGFloat(finish),clockwise:false)
                c.strokePath()
                for p in 0..<3 {
                    let angle = side == -1 ? Double.pi*(0.62+Double(p)*0.15) : Double.pi*(0.38-Double(p)*0.15)
                    c.saveGState()
                    c.translateBy(x:CGFloat(Darwin.cos(angle)*64),y:CGFloat(10+Darwin.sin(angle)*64))
                    c.rotate(by:CGFloat(angle + side*0.55))
                    c.fillEllipse(in:CGRect(x:-13,y:-8,width:26,height:16)); c.restoreGState()
                }
            }
            let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center
            let attrs:[NSAttributedString.Key:Any] = [
                .font:UIFont(name:"Verdana-Bold",size:108) ?? UIFont.boldSystemFont(ofSize:108),
                .foregroundColor:glyph,.strokeColor:kintaraColor(0x140B26),.strokeWidth:-10,
                .paragraphStyle:paragraph
            ]
            NSString(string:"1").draw(in:CGRect(x:-70,y:-54,width:140,height:130),withAttributes:attrs)
            c.restoreGState()
        }
    }
}

private struct CharacterThumbnail: View {
    let image: UIImage?
    let hasSession: Bool

    var body: some View {
        ZStack {
            Circle()
                .fill(.white.opacity(0.08))

            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .padding(2)
            } else {
                Image(systemName: hasSession
                      ? "person.crop.circle.badge.checkmark"
                      : "person.crop.circle.badge.exclamationmark")
                    .font(.system(size: 23, weight: .semibold))
            }
        }
        .frame(width: 48, height: 48)
        .clipShape(Circle())
        .overlay(Circle().stroke(.white.opacity(0.10), lineWidth: 1))
    }
}

private struct CharacterStatsView: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dismiss) private var dismiss

    private let paper = Color(red: 0.91, green: 0.895, blue: 0.855)
    private let ink = Color(red: 0.16, green: 0.15, blue: 0.14)
    private let copper = Color(red: 0.67, green: 0.34, blue: 0.23)

    var body: some View {
        ZStack {
            PaperTexture()
            GeometryReader { proxy in
                let designWidth: CGFloat = 430
                let designHeight: CGFloat = 860
                let scale = min(proxy.size.width / designWidth, proxy.size.height / designHeight)

                VStack(spacing: 12) {
                    HStack {
                        Button("Fechar") { dismiss() }
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                        Spacer()
                        Text("STATS")
                            .font(.system(size: 23, weight: .bold, design: .rounded))
                        Spacer()
                        Button {
                            Task { await app.refreshCharacterProfile(force: true) }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 18, weight: .bold))
                        }
                    }
                    .foregroundStyle(ink)
                    .padding(.horizontal, 6)
                    .frame(height: 42)

                    HStack(spacing: 14) {
                        ZStack {
                            CharacterVoxel3DView(appearance: app.characterProfile.appearance)
                                .padding(5)
                        }
                        .frame(width: 104, height: 126)
                        .embossedPanel(cornerRadius: 18, fill: paper)

                        VStack(alignment: .leading, spacing: 6) {
                            Text(app.characterProfile.displayName)
                                .font(.system(size: 25, weight: .bold, design: .rounded))
                                .foregroundStyle(ink)
                                .lineLimit(1)
                            Text("Lvl \(app.characterProfile.totalLevel)")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                                .foregroundStyle(copper)
                            HStack(spacing: 7) {
                                Circle()
                                    .fill(app.hasSession ? Color(red: 0.42, green: 0.54, blue: 0.39) : .gray)
                                    .frame(width: 9, height: 9)
                                Text(app.hasSession ? "Conta conectada" : "Sem sessão")
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                            }
                            .foregroundStyle(ink.opacity(0.72))
                        }
                        Spacer()
                    }

                    if app.characterProfileLoading && !app.characterProfile.loaded {
                        ProgressView("Carregando Stats…").tint(copper)
                        Spacer()
                    } else {
                        VStack(spacing: 8) {
                            ForEach(CharacterSkill.allCases) { skill in
                                statRow(skill)
                            }
                        }
                        .padding(14)
                        .embossedPanel(cornerRadius: 20, fill: paper)

                        HStack {
                            Text("Total Level")
                                .font(.system(size: 19, weight: .bold, design: .rounded))
                            Spacer()
                            Text("\(app.characterProfile.totalLevel)")
                                .font(.system(size: 28, weight: .bold, design: .rounded))
                                .foregroundStyle(copper)
                        }
                        .foregroundStyle(ink)
                        .padding(.horizontal, 18)
                        .frame(height: 66)
                        .embossedPanel(cornerRadius: 18, fill: paper)
                        Spacer(minLength: 0)
                    }
                }
                .padding(16)
                .frame(width: designWidth, height: designHeight, alignment: .top)
                .scaleEffect(scale, anchor: .top)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }
        }
        .preferredColorScheme(.light)
        .task { await app.refreshCharacterProfile(force: true) }
    }

    private func statRow(_ skill: CharacterSkill) -> some View {
        let stats = app.characterProfile.skills
        let level = stats.level(for: skill)
        return VStack(spacing: 5) {
            HStack {
                Text(skill.localizedName)
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundStyle(ink)
                    .frame(width: 86, alignment: .leading)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color(red: 0.82, green: 0.80, blue: 0.75))
                        Capsule().fill(copper)
                            .frame(width: max(6, geo.size.width * stats.progress(for: skill)))
                    }
                }
                .frame(height: 12)
                Text("\(level)/40")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(ink)
                    .monospacedDigit()
                    .frame(width: 42, alignment: .trailing)
            }
            HStack {
                Spacer().frame(width: 94)
                Text("\(stats.currentLevelXP(for: skill)) / \(stats.currentLevelXPGoal(for: skill)) XP")
                    .font(.system(size: 10.5, weight: .medium, design: .rounded))
                    .foregroundStyle(ink.opacity(0.55))
                    .monospacedDigit()
                Spacer()
            }
        }
    }
}

private struct CharacterSkillCard: View {
    let skill: CharacterSkill
    let stats: CharacterSkillStats
    let compact: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 7 : 9) {
            HStack(spacing: 8) {
                Image(systemName: skill.icon)
                    .foregroundStyle(.cyan)
                    .frame(width: 20)
                Text(skill.localizedName)
                    .font(.subheadline.bold())
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text("\(stats.level(for: skill))/\(CharacterSkillStats.maxLevel)")
                    .font(.caption.bold().monospacedDigit())
            }

            ProgressView(value: stats.progress(for: skill))
                .tint(.green)

            if stats.level(for: skill) >= CharacterSkillStats.maxLevel {
                Text("Nível máximo")
                    .font(.caption2.bold())
                    .foregroundStyle(.green)
            } else {
                Text("\(stats.currentLevelXP(for: skill).formatted()) / \(stats.currentLevelXPGoal(for: skill).formatted()) XP no nível")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.white.opacity(0.82))
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }

            Text("\(stats.totalXP(for: skill).formatted()) XP total")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
        .padding(compact ? 11 : 13)
        .frame(maxWidth: .infinity, minHeight: compact ? 88 : 98, alignment: .leading)
        .background(.white.opacity(0.065), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(.white.opacity(0.075), lineWidth: 1)
        )
    }
}

private struct CharacterArtworkCaptureView: UIViewRepresentable {
    let cookie: String
    let onCapture: (UIImage) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onCapture: onCapture)
    }

    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: Coordinator.handlerName)
        controller.addUserScript(WKUserScript(
            source: Coordinator.bridgeScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController = controller

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false
        context.coordinator.webView = webView
        context.coordinator.load(cookie: cookie)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.stopLoading()
        webView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.handlerName)
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        static let handlerName = "kintaraCharacter"
        static let bridgeScript = """
        (() => {
          if (window.__kintaraIOSCharacterBridge) return;
          window.__kintaraIOSCharacterBridge = true;
          window.addEventListener('message', (event) => {
            const value = event && event.data;
            if (value && value.t === 'kintara_outfit_embed_ready') {
              window.webkit.messageHandlers.kintaraCharacter.postMessage({ t: 'ready' });
            }
          });
        })();
        """

        weak var webView: WKWebView?
        private let onCapture: (UIImage) -> Void
        private var captured = false
        private var attempts = 0

        init(onCapture: @escaping (UIImage) -> Void) {
            self.onCapture = onCapture
        }

        func load(cookie rawCookie: String) {
            guard let webView,
                  let cookie = Self.makeSessionCookie(rawCookie),
                  let url = URL(string: "https://kintara.com/play?embed=outfit")
            else { return }

            webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { [weak webView] in
                var request = URLRequest(url: url)
                request.cachePolicy = .reloadIgnoringLocalCacheData
                webView?.load(request)
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard !captured,
                  let body = message.body as? [String: Any],
                  body["t"] as? String == "ready"
            else { return }
            captureAfterRenderDelay()
        }

        private func captureAfterRenderDelay() {
            guard !captured, attempts < 8 else { return }
            attempts += 1
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
                self?.captureCanvas()
            }
        }

        private func captureCanvas() {
            guard let webView, !captured else { return }
            let script = """
            (() => {
              const canvas = document.querySelector('#kintara-dash-outfit-letter canvas');
              if (!canvas || canvas.width < 64 || canvas.height < 64) return null;
              try { return canvas.toDataURL('image/png'); } catch (_) { return null; }
            })();
            """
            webView.evaluateJavaScript(script) { [weak self] result, _ in
                guard let self else { return }
                guard let dataURL = result as? String,
                      let comma = dataURL.firstIndex(of: ","),
                      let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])),
                      let image = UIImage(data: data)
                else {
                    self.captureAfterRenderDelay()
                    return
                }
                self.captured = true
                self.onCapture(image)
            }
        }

        private static func makeSessionCookie(_ raw: String) -> HTTPCookie? {
            let pair = raw.split(separator: ";", maxSplits: 1).first.map(String.init) ?? raw
            let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
            guard parts.count == 2,
                  parts[0] == "kintara_session",
                  !parts[1].isEmpty
            else { return nil }

            return HTTPCookie(properties: [
                .domain: ".kintara.com",
                .path: "/",
                .name: parts[0],
                .value: parts[1],
                .secure: "TRUE"
            ])
        }
    }
}

private struct FullLogView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false
    @State private var exportedLogFile: ExportedLogFile?
    @State private var exportError: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 7) {
                            if app.diagnosticLogs.isEmpty {
                                ContentUnavailableView(
                                    "Sem logs",
                                    systemImage: "doc.text",
                                    description: Text("Inicie uma sessão ou atividade para registrar o diagnóstico.")
                                )
                                .frame(maxWidth: .infinity)
                                .padding(.top, 50)
                            } else {
                                ForEach(Array(app.diagnosticLogs.enumerated()), id: \.offset) { index, line in
                                    Text(line)
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundStyle(.white.opacity(0.86))
                                        .textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .id(index)
                                }
                            }
                        }
                        .padding()
                    }
                    .onAppear { scrollToBottom(proxy) }
                    .onChange(of: app.diagnosticLogs.count) { _, _ in scrollToBottom(proxy) }
                }
            }
            .navigationTitle("Log completo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fechar") { dismiss() }
                }
                ToolbarItemGroup(placement: .primaryAction) {
                    Button {
                        UIPasteboard.general.string = app.fullLogText
                        copied = true
                    } label: {
                        Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    }
                    .disabled(app.diagnosticLogs.isEmpty)
                    .accessibilityLabel("Copiar log completo")

                    Button {
                        exportLogAsTXT()
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .disabled(app.diagnosticLogs.isEmpty)
                    .accessibilityLabel("Exportar log em TXT")

                    Button(role: .destructive) {
                        app.clearDiagnosticLogs()
                    } label: {
                        Image(systemName: "trash")
                    }
                    .disabled(app.diagnosticLogs.isEmpty)
                    .accessibilityLabel("Limpar log completo")
                }
            }
        }
        .sheet(item: $exportedLogFile, onDismiss: cleanupExportedLogFile) { file in
            ShareSheet(activityItems: [file.url])
        }
        .alert(
            "Não foi possível exportar o log",
            isPresented: Binding(
                get: { exportError != nil },
                set: { if !$0 { exportError = nil } }
            )
        ) {
            Button("OK", role: .cancel) { exportError = nil }
        } message: {
            Text(exportError ?? "Erro desconhecido")
        }
    }

    private func exportLogAsTXT() {
        guard !app.diagnosticLogs.isEmpty else { return }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"

        let fileName = "KintTany-log-\(formatter.string(from: Date())).txt"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)

        do {
            try app.fullLogText.write(to: url, atomically: true, encoding: .utf8)
            exportedLogFile = ExportedLogFile(url: url)
        } catch {
            exportError = error.localizedDescription
        }
    }

    private func cleanupExportedLogFile() {
        guard let url = exportedLogFile?.url else { return }
        try? FileManager.default.removeItem(at: url)
        exportedLogFile = nil
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        guard !app.diagnosticLogs.isEmpty else { return }
        let last = app.diagnosticLogs.count - 1
        DispatchQueue.main.async {
            proxy.scrollTo(last, anchor: .bottom)
        }
    }
}


private struct ExportedLogFile: Identifiable {
    let id = UUID()
    let url: URL
}

private struct ShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
