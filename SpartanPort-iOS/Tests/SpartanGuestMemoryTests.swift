import XCTest
@testable import SpartanPort

final class SpartanGuestMemoryTests: XCTestCase {
    func testAllocatesBoundedDataOnlyGuestArena() throws {
        let memory = try XCTUnwrap(spartan_guest_memory_create(8192))
        defer { spartan_guest_memory_destroy(memory) }

        // The public VM allocator rounds to the device's page size (4 KiB on
        // some targets, 16 KiB on current iOS simulators). Assert against the
        // actual arena boundary rather than the requested byte count.
        let arenaSize = spartan_guest_memory_size(memory)
        XCTAssertGreaterThanOrEqual(arenaSize, 8192)
        XCTAssertNotNil(spartan_guest_memory_host_pointer(memory, 0, 16))
        XCTAssertNotNil(spartan_guest_memory_host_pointer(memory, arenaSize, 0))
        XCTAssertNil(spartan_guest_memory_host_pointer(memory, arenaSize, 1))
        XCTAssertNil(spartan_guest_memory_host_pointer(memory, UInt64.max, 1))
    }

    func testProtectRejectsExecutablePages() throws {
        let memory = try XCTUnwrap(spartan_guest_memory_create(4096))
        defer { spartan_guest_memory_destroy(memory) }

        XCTAssertEqual(spartan_guest_memory_protect(memory, 0, 4096, PROT_READ), 0)
        XCTAssertEqual(spartan_guest_memory_protect(memory, 0, 4096, PROT_READ | PROT_WRITE), 0)
        XCTAssertEqual(spartan_guest_memory_protect(memory, 0, 4096, PROT_READ | PROT_EXEC), -1)
    }
}
