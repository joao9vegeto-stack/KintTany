#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
ENGINE = ROOT / 'KintTany/Bot/AutomationEngine.swift'
TESTS = ROOT / 'KintTanyTests/RealtimeProtocolTests.swift'
PROJECT = ROOT / 'KintTany.xcodeproj/project.pbxproj'
OLD_REF = '55dda5bdd8312a9e8c30830a00caa2a9089a56fe'


def git_show(path: str) -> str:
    return subprocess.check_output(['git', 'show', f'{OLD_REF}:{path}'], text=True)


def brace_block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f'not found: {signature}')
    open_brace = text.find('{', start)
    if open_brace < 0:
        raise RuntimeError(f'no opening brace: {signature}')
    depth = 0
    in_string = False
    escaped = False
    for i in range(open_brace, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise RuntimeError(f'unclosed block: {signature}')


def replace_block(text: str, signature: str, replacement: str) -> str:
    old = brace_block(text, signature)
    return text.replace(old, replacement, 1)


def insert_after_block(text: str, signature: str, addition: str) -> str:
    old = brace_block(text, signature)
    if addition.strip() in text:
        return text
    return text.replace(old, old + '\n\n' + addition.rstrip(), 1)


def insert_before(text: str, marker: str, block: str) -> str:
    if block.strip() in text:
        return text
    i = text.find(marker)
    if i < 0:
        raise RuntimeError(f'marker not found: {marker}')
    return text[:i] + block + text[i:]


def must_replace(text: str, old: str, new: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f'expected {count}, found {actual}: {old[:100]}')
    return text.replace(old, new, count)


def add_tests() -> None:
    text = TESTS.read_text()

    modern_payload_test = r'''func testStableSaveBackpackPayloadUsesCurrentOfficialContract() throws {
        let armor: [Any] = [["t": "armor_test", "n": 1]]
        let backpack: [String: Any] = [
            "wood": 10, "potion_health_l2": 2, "silver_ore": 7, "cacti": 3,
            "bait_feather": 11, "bait_trout": 4, "bait_bass": 2, "bait_tuna": 1,
            "fish_trout": 9, "fish_bass": 8, "fish_tuna": 6, "bankPages": 3,
            "invSlots": [NSNull()], "hotbar": [NSNull()], "armorSlots": armor,
            "mountSlots": [NSNull()], "cosmeticSlots": [NSNull()],
            "petSlots": [NSNull()], "furnitureSlots": [NSNull()], "bankSlots": [NSNull()],
            "equippedHotbar": 0, "mountDragonRiding": true
        ]
        let body = BackpackSavePayloadPolicy.makeBody(
            backpack: backpack, baseSeq: 321, fleet: "us", shardID: 4
        )
        XCTAssertEqual(RealtimeProtocol.int(body["baseSeq"]), 321)
        XCTAssertEqual(body["fleet"] as? String, "us")
        XCTAssertEqual(RealtimeProtocol.int(body["shardId"]), 4)
        XCTAssertNotNil(body["intentionalRemovals"])
        XCTAssertNotNil(body["intentionalRelicRemovals"])
        XCTAssertEqual((body["armorSlots"] as? [Any])?.count, armor.count)
        XCTAssertEqual(RealtimeProtocol.int(body["bankPages"]), 3)
        XCTAssertEqual(RealtimeProtocol.int(body["silver_ore"]), 7)
        XCTAssertEqual(RealtimeProtocol.int(body["cacti"]), 3)
        XCTAssertEqual(RealtimeProtocol.int(body["bait_feather"]), 11)
        XCTAssertEqual(RealtimeProtocol.int(body["fish_trout"]), 9)
        XCTAssertEqual(RealtimeProtocol.bool(body["mountDragonRiding"]), true)
        let resources = try XCTUnwrap(body["resources"] as? [String: Any])
        XCTAssertEqual(RealtimeProtocol.int(resources["potion_health_l2"]), 2)
    }'''
    text = replace_block(
        text,
        'func testStableSaveBackpackPayloadUsesExactV30FinalContract() throws',
        modern_payload_test
    )

    stale_test = r'''func testStaleSaveAllowsExactlyOneAuthoritativeReconstruction() throws {
        XCTAssertEqual(BankMutationPolicy.postMovementSettlingMS, 1_200)
        XCTAssertEqual(BankMutationPolicy.maximumSaveAttempts, 2)
        XCTAssertTrue(BankMutationPolicy.isStaleSave("stale_save"))
        XCTAssertFalse(BankMutationPolicy.isStaleSave("rate_limited"))
        let payload: [String: Any] = [
            "authoritative": ["currentStateSeq": 88, "currentBackpack": ["wood": 42]]
        ]
        let state = try XCTUnwrap(BankMutationPolicy.authoritativeState(from: payload))
        XCTAssertEqual(state.stateSeq, 88)
        XCTAssertEqual(RealtimeProtocol.int(state.backpack["wood"]), 42)
    }'''
    text = replace_block(
        text,
        'func testBankMutationKeepsBuild43SingleSnapshotTransactionShape()',
        stale_test
    )

    marker = '    func testDunesHeatSafetyUsesThirtyHPThresholdOnlyForDunes() {\n'
    extra = r'''    func testItemConservationDetectsMissingToolAndAllowsBankMove() {
        let before: [String: Any] = [
            "hotbar": [["t": "tool_pickaxe", "durability": 91]],
            "invSlots": [NSNull()], "bankSlots": [NSNull()]
        ]
        let moved: [String: Any] = [
            "hotbar": [NSNull()], "invSlots": [NSNull()],
            "bankSlots": [["t": "tool_pickaxe", "durability": 91]]
        ]
        let missing: [String: Any] = [
            "hotbar": [NSNull()], "invSlots": [NSNull()], "bankSlots": [NSNull()]
        ]
        XCTAssertTrue(ItemConservationPolicy.isConserved(type: "tool_pickaxe", before: before, after: moved))
        XCTAssertFalse(ItemConservationPolicy.isConserved(type: "tool_pickaxe", before: before, after: missing))
        XCTAssertEqual(ItemConservationPolicy.total(type: "tool_pickaxe", in: before), 1)
    }

    func testDunesSuspiciousSnapshotHPRequiresAuthoritativeHTTPConfirmation() {
        XCTAssertTrue(DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: 100, snapshotHP: 20, conservativeHP: 99, region: "desert"
        ))
        XCTAssertFalse(DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: 100, snapshotHP: 99, conservativeHP: 99, region: "desert"
        ))
        XCTAssertFalse(DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: 100, snapshotHP: 20, conservativeHP: 99, region: "eldergrove"
        ))
    }

'''
    text = insert_before(text, marker, extra)
    TESTS.write_text(text)

def apply_impl() -> None:
    current = ENGINE.read_text()
    old = git_show('KintTany/Bot/AutomationEngine.swift')

    # Restore only the modern persistence primitives from the pre-rollback implementation.
    current = replace_block(current, 'struct BankMutationPolicy', brace_block(old, 'struct BankMutationPolicy'))
    current = replace_block(current, 'struct BackpackSavePayloadPolicy', brace_block(old, 'struct BackpackSavePayloadPolicy'))
    current = replace_block(current, 'private enum HTTPError', brace_block(old, 'private enum HTTPError'))

    # Bring back the known-good mutation functions without replacing later Build 66 engine work.
    for signature in [
        'func ensurePotionLoadout(targets: [String: Int]) async throws -> BackpackState',
        'func ensureCarriedItem(type: String, quantity targetRaw: Int, preferHotbar: Bool) async throws -> Int',
        'private func depositIntoBank(_ wanted: [String: Int], sourceKeys: [String]) async throws -> BankDepositResult',
        'private func saveBackpack(_ backpack: [String: Any], baseSeq: Int) async throws -> [String: Any]',
        'private func requestAny(method: String, path: String, body: [String: Any]?) async throws -> Any',
    ]:
        current = replace_block(current, signature, brace_block(old, signature))

    # Insert stale reconstruction helpers from the old modern implementation.
    fresh = brace_block(old, 'private func freshBackpackState() async throws -> BackpackState')
    retry = brace_block(old, 'private func withFreshBankMutation<T>')
    # Do not keep the former synthetic query-string cache buster; current requestAny already sends no-cache.
    fresh = '''private func freshBackpackState() async throws -> BackpackState {
        try await backpackState()
    }'''
    backpack_fn = brace_block(current, 'func backpackState() async throws -> BackpackState')
    if 'private func withFreshBankMutation<T>' not in current:
        current = current.replace(backpack_fn, backpack_fn + '\n\n    ' + fresh.replace('\n', '\n    ') + '\n\n    ' + retry.replace('\n', '\n    '), 1)

    conservation = r'''struct ItemConservationPolicy {
    static func slotCount(_ value: Any?, type: String) -> Int {
        guard let slots = value as? [Any] else { return 0 }
        return slots.reduce(0) { partial, raw in
            guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return partial }
            return partial + CombatBankFirstPolicy.slotQuantity(slot)
        }
    }

    static func total(type: String, in backpack: [String: Any]) -> Int {
        slotCount(backpack["hotbar"], type: type)
            + slotCount(backpack["invSlots"], type: type)
            + slotCount(backpack["bankSlots"], type: type)
    }

    static func isConserved(type: String, before: [String: Any], after: [String: Any]) -> Bool {
        total(type: type, in: before) == total(type: type, in: after)
    }
}'''
    current = insert_after_block(current, 'struct BackpackSavePayloadPolicy', conservation)

    # Replace ensureCarriedItem with a stale-safe reconstruction plus total-item conservation.
    carried_impl = r'''func ensureCarriedItem(type: String, quantity targetRaw: Int, preferHotbar: Bool) async throws -> Int {
        let initial = try await freshBackpackState()
        let initialTotal = ItemConservationPolicy.total(type: type, in: initial.backpack)
        let carried: Int = try await withFreshBankMutation { state in
            let target = max(1, targetRaw)
            var backpack = state.backpack
            var hotbar = backpack["hotbar"] as? [Any] ?? Array(repeating: NSNull(), count: 6)
            var inv = backpack["invSlots"] as? [Any] ?? Array(repeating: NSNull(), count: 24)
            var bank = backpack["bankSlots"] as? [Any] ?? []
            let before = InventoryLoadoutAllocator.carriedCount(type: type, hotbar: hotbar, inventory: inv)
            if before >= target { return before }
            let moved = InventoryLoadoutAllocator.withdraw(
                type: type, quantity: target, preferHotbar: preferHotbar,
                hotbar: &hotbar, inventory: &inv, bank: &bank
            )
            guard moved > 0 else { return before }
            backpack["hotbar"] = hotbar
            backpack["invSlots"] = inv
            backpack["bankSlots"] = bank
            if backpack[type] != nil {
                backpack[type] = max(0, RealtimeProtocol.int(backpack[type]) ?? 0) + moved
            }
            _ = try await saveBackpack(backpack, baseSeq: state.stateSeq)
            let freshState = try await freshBackpackState()
            let freshHotbar = freshState.backpack["hotbar"] as? [Any] ?? []
            let freshInv = freshState.backpack["invSlots"] as? [Any] ?? []
            return InventoryLoadoutAllocator.carriedCount(type: type, hotbar: freshHotbar, inventory: freshInv)
        }
        let final = try await freshBackpackState()
        let finalTotal = ItemConservationPolicy.total(type: type, in: final.backpack)
        guard finalTotal == initialTotal else {
            throw HTTPError.server("item_conservation_failed: \(type) total \(initialTotal)→\(finalTotal)")
        }
        return carried
    }'''
    current = replace_block(current, 'func ensureCarriedItem(type: String, quantity targetRaw: Int, preferHotbar: Bool) async throws -> Int', carried_impl)

    # Deposit confirmation must also prove that carried+bank is conserved.
    old_fragment = '''            let bankIncrease = max(0, b1 - b0)\n            let carriedDecrease = max(0, c0 - c1)\n            diagnostics.append("\\(type) • solicitado=\\(wanted[type] ?? expected) movido=\\(expected) • banco \\(b0)→\\(b1) • carregado \\(c0)→\\(c1)")\n\n            if bankIncrease >= expected && carriedDecrease >= expected {'''
    new_fragment = '''            let bankIncrease = max(0, b1 - b0)\n            let carriedDecrease = max(0, c0 - c1)\n            let conserved = (b0 + c0) == (b1 + c1)\n            diagnostics.append("\\(type) • solicitado=\\(wanted[type] ?? expected) movido=\\(expected) • banco \\(b0)→\\(b1) • carregado \\(c0)→\\(c1) • total \\(b0 + c0)→\\(b1 + c1)")\n\n            if bankIncrease >= expected && carriedDecrease >= expected && conserved {'''
    current = must_replace(current, old_fragment, new_fragment)

    # Dunes final preflight: no Presence if the selected tool changed total or is no longer carried.
    preflight = brace_block(current, 'static func prepareDunesPreflight(for mode: ActivityMode, cookie: String) async throws -> (tool: String, healthPotionPlus: Int)')
    preflight = preflight.replace(
        '        var selected: String? = best.carried >= 1 ? best.type : nil\n',
        '        let selectedInitialTotal = best.carried + best.bank\n        var selected: String? = best.carried >= 1 ? best.type : nil\n', 1
    )
    preflight = preflight.replace(
        '        guard deposit.unresolved.isEmpty else {\n            throw EngineError.bankDepositFailed(deposit.unresolved.joined(separator: ", "))\n        }\n        return (selected, healthPotionPlus)\n',
        '''        guard deposit.unresolved.isEmpty else {\n            throw EngineError.bankDepositFailed(deposit.unresolved.joined(separator: ", "))\n        }\n        let finalTool = try await client.itemLocationCounts(type: selected)\n        let selectedFinalTotal = finalTool.carried + finalTool.bank\n        guard selectedFinalTotal == selectedInitialTotal else {\n            throw EngineError.bankDepositFailed("conservação de \\(ActivityToolPolicy.displayName(selected)) falhou • total \\(selectedInitialTotal)→\\(selectedFinalTotal)")\n        }\n        guard finalTool.carried >= 1 else {\n            throw EngineError.gatherLoadoutNotReady(ActivityToolPolicy.displayName(selected))\n        }\n        return (selected, healthPotionPlus)\n''', 1
    )
    current = replace_block(current, 'static func prepareDunesPreflight(for mode: ActivityMode, cookie: String) async throws -> (tool: String, healthPotionPlus: Int)', preflight)

    # Source-aware Dunes HP: a generic snapshot that falls faster than heat gets /me confirmation.
    hp_policy = r'''struct DunesSnapshotHPPolicy {
    static func requiresHTTPConfirmation(currentHP: Int, snapshotHP: Int, conservativeHP: Int, region: String) -> Bool {
        GatherRegionPolicy.isDunesRegion(region)
            && snapshotHP < currentHP
            && snapshotHP < conservativeHP
    }
}'''
    current = insert_after_block(current, 'struct OwnVitalsPolicy', hp_policy)
    current = must_replace(
        current,
        '    private var lastTrustedOwnHPAtMS: Double?\n    private var lastTrustedOwnHPRegion: String?\n',
        '    private var lastTrustedOwnHPAtMS: Double?\n    private var lastTrustedOwnHPRegion: String?\n    private var ownHPRevision = 0\n'
    )
    current = must_replace(
        current,
        '            if let hp = RealtimeProtocol.int(me["php"]) { recordTrustedOwnHP(hp, regionHint: serverRegion) }',
        '            if let hp = RealtimeProtocol.int(me["php"]) { await recordSnapshotOwnHP(hp, source: "snap.players", regionHint: serverRegion) }',
        1
    )
    current = must_replace(
        current,
        '            if let hp = RealtimeProtocol.int(me["php"]) { recordTrustedOwnHP(hp, regionHint: serverRegion) }',
        '            if let hp = RealtimeProtocol.int(me["php"]) { await recordSnapshotOwnHP(hp, source: "snap.playersVital", regionHint: serverRegion) }',
        1
    )
    current = must_replace(
        current,
        '    private func recordTrustedOwnHP(_ hp: Int, regionHint: String? = nil) {\n        playerHP = hp\n',
        '    private func recordTrustedOwnHP(_ hp: Int, regionHint: String? = nil) {\n        playerHP = hp\n        ownHPRevision += 1\n'
    )
    hp_helper = r'''    private func recordSnapshotOwnHP(_ hp: Int, source: String, regionHint: String? = nil) async {
        let trustedRegion = (regionHint ?? serverRegion ?? region)
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let conservative = estimatedDunesHPFromMonotonicClock()
        guard DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: playerHP, snapshotHP: hp, conservativeHP: conservative, region: trustedRegion
        ) else {
            recordTrustedOwnHP(hp, regionHint: trustedRegion)
            return
        }
        let revision = ownHPRevision
        reporter(.diagnostic("[DUNES][HP] snapshot suspeito • fonte=\(source) • atual=\(playerHP) • snapshot=\(hp) • conservador=\(conservative)"))
        do {
            let me = try await http.get("/api/auth/me")
            guard ownHPRevision == revision else {
                reporter(.diagnostic("[DUNES][HP] confirmação descartada • vital mais novo chegou durante /me"))
                return
            }
            if let player = me["player"] as? [String: Any],
               let authoritativeHP = RealtimeProtocol.int(player["php"] ?? player["hp"]) {
                reporter(.diagnostic("[DUNES][HP] snapshot=\(hp) • /me=\(authoritativeHP) • fonte=\(source)"))
                recordTrustedOwnHP(authoritativeHP, regionHint: trustedRegion)
                return
            }
        } catch {
            reporter(.diagnostic("[DUNES][HP] /me indisponível • fail-safe aceita HP baixo • \(error.localizedDescription)"))
        }
        if ownHPRevision == revision { recordTrustedOwnHP(hp, regionHint: trustedRegion) }
    }

'''
    current = insert_before(current, '    private func hasRecentTrustedDunesHP(maxAgeMS: Double = 5_000) -> Bool {\n', hp_helper)

    # persistLoot is another save-backpack caller; route it through the modern builder.
    persist_old = '''        let body = BackpackSavePayloadPolicy.makeBody(backpack: backpack, baseSeq: stateSeq)\n\n        let response = try await post("/api/auth/save-backpack", body: body)\n        guard RealtimeProtocol.bool(response["ok"]) != false else {\n            throw HTTPError.server((response["error"] as? String) ?? "save-backpack recusado")\n        }\n'''
    persist_new = '''        let response = try await saveBackpack(backpack, baseSeq: stateSeq)\n'''
    current = must_replace(current, persist_old, persist_new)

    ENGINE.write_text(current)

    project = PROJECT.read_text().replace('CURRENT_PROJECT_VERSION = 66;', 'CURRENT_PROJECT_VERSION = 67;')
    if project.count('CURRENT_PROJECT_VERSION = 67;') != 2:
        raise RuntimeError('expected exactly two build 67 settings')
    PROJECT.write_text(project)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {'tests', 'impl'}:
        raise SystemExit('usage: apply_build67.py tests|impl')
    if sys.argv[1] == 'tests':
        add_tests()
    else:
        apply_impl()


if __name__ == '__main__':
    main()
