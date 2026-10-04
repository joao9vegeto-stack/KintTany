#!/usr/bin/env bash
set -euo pipefail

SRC="${1:-source}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

test -d "$SRC/ios"
cp "$ROOT/config/VitaJoN.entitlements" "$SRC/ios/VitaJoN.entitlements"

python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])

info = src / "ios" / "Info.plist.in"
s = info.read_text()
s = s.replace("<string>Tsubomi</string>", "<string>VitaJoN</string>")
s = s.replace("<string>0.47.0</string>", "<string>0.47.8</string>", 1)
s = s.replace("<string>470</string>", "<string>478</string>", 1)
info.write_text(s)

state = src / "vita3k" / "config" / "include" / "config" / "state.h"
s = state.read_text()
old = "float resolution_multiplier = 1.0f;"
if old not in s:
    raise SystemExit("resolution default anchor not found")
s = s.replace(old, "float resolution_multiplier = 0.75f;", 1)
old = 'std::string memory_mapping = "double-buffer";'
if old not in s:
    raise SystemExit("memory mapping default anchor not found")
s = s.replace(old, 'std::string memory_mapping = "disabled";', 1)
state.write_text(s)

cmake = src / "ios" / "CMakeLists.txt"
s = cmake.read_text()
anchor = '    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${VITA3K_IOS_BUNDLE_ID}"\n'
if anchor not in s:
    raise SystemExit("CMake bundle-id anchor not found")
if "XCODE_ATTRIBUTE_CODE_SIGN_ENTITLEMENTS" not in s:
    s = s.replace(
        anchor,
        anchor + '    XCODE_ATTRIBUTE_CODE_SIGN_ENTITLEMENTS "${CMAKE_CURRENT_SOURCE_DIR}/VitaJoN.entitlements"\n',
        1,
    )
cmake.write_text(s)


upstream = src / "ios" / "src" / "UpstreamMain.cpp"
s = upstream.read_text()

old = """    bool app_terminating = false;
    bool jit_pool_prewarmed = g_jit_pool_ready.load(std::memory_order_relaxed);
    while (!app_terminating) {
    auto launch_request = choose_boot_title(*emuenv);
    if (!launch_request)
        break;
"""
new = """    bool app_terminating = false;
    bool jit_pool_prewarmed = g_jit_pool_ready.load(std::memory_order_relaxed);
    std::optional<AppLaunchRequest> pending_relaunch;
    while (!app_terminating) {
    auto launch_request = pending_relaunch
        ? std::exchange(pending_relaunch, std::nullopt)
        : choose_boot_title(*emuenv);
    if (!launch_request)
        break;
"""
if old not in s:
    raise SystemExit("iOS LoadExec outer-loop anchor not found")
s = s.replace(old, new, 1)

old = "    if (!session_controller.begin_launch(*launch_request)) {"
new = "    if (!session_controller.begin_launch(*launch_request, launch_request->reason != AppLaunchReason::LoadExec)) {"
if old not in s:
    raise SystemExit("iOS begin_launch anchor not found")
s = s.replace(old, new, 1)

old = """        if (auto request = emuenv->take_app_launch_request()) {
            // In-process relaunch (LoadExec) is not supported yet on iOS.
            LOG_WARN("Title requested relaunch of '{}'; stopping instead.", request->self_path);
            running = false;
        }
"""
new = """        if (auto request = emuenv->take_app_launch_request()) {
            LOG_INFO("iOS handling in-process relaunch: app='{}' self='{}'",
                request->app_path, request->self_path);
            pending_relaunch = std::move(*request);
            running = false;
        }
"""
if old not in s:
    raise SystemExit("iOS LoadExec request anchor not found")
s = s.replace(old, new, 1)

old = """    session_controller.stop(app_terminating
            ? app::AppSessionStopReason::FrontendShutdown
            : app::AppSessionStopReason::UserRequest);
"""
new = """    const bool relaunching = pending_relaunch.has_value() && !app_terminating;
    session_controller.stop(app_terminating
            ? app::AppSessionStopReason::FrontendShutdown
            : relaunching
                ? app::AppSessionStopReason::Relaunch
                : app::AppSessionStopReason::UserRequest);
"""
if old not in s:
    raise SystemExit("iOS stop-reason anchor not found")
s = s.replace(old, new, 1)

old = """    emuenv->audio.adapter.reset();
    emuenv->audio.audio_backend.clear();
    restore_global_config();

    LOG_INFO("Returning to game library");
"""
new = """    emuenv->audio.adapter.reset();
    emuenv->audio.audio_backend.clear();
    if (relaunching && session_settings)
        g_pending_game_settings = session_settings;
    restore_global_config();

    if (relaunching)
        LOG_INFO("Relaunching iOS session in-process with self '{}'", pending_relaunch->self_path);
    else
        LOG_INFO("Returning to game library");
"""
if old not in s:
    raise SystemExit("iOS relaunch cleanup anchor not found")
s = s.replace(old, new, 1)

upstream.write_text(s)

print("VitaJoN source patch applied")
PY


# PCSA00029 graphics fixes derived from the device log and selected Vita3K+ fixes.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])

# Uncharted profile: high accuracy disables the fast texture-viewport path,
# while iOS staging-buffer surface sync keeps framebuffer-backed guest memory coherent.
upstream = src / "ios" / "src" / "UpstreamMain.cpp"
s = upstream.read_text()
old = """    if (session_settings)
        apply_game_session_settings(*emuenv, *session_settings);

    IOSFrameHost frame_host(window);
"""
new = """    if (session_settings)
        apply_game_session_settings(*emuenv, *session_settings);

    if (launch_request->app_path == "PCSA00029") {
        auto &current = emuenv->cfg.current_config;
        current.resolution_multiplier = 1.0f;
        current.high_accuracy = true;
        current.disable_surface_sync = false;
        current.memory_mapping = "double-buffer";
        current.anisotropic_filtering = 1;
        current.screen_filter = "Nearest";
        current.async_pipeline_compilation = false;
        LOG_INFO("VitaJoN Uncharted profile: res=1x high_accuracy=true surface_sync=true memory=double-buffer aniso=1 filter=Nearest async=false");
    }

    IOSFrameHost frame_host(window);
"""
if old not in s:
    raise SystemExit("Uncharted renderer profile anchor not found")
s = s.replace(old, new, 1)
upstream.write_text(s)

# When a framebuffer-backed texture only partially overlaps the cached surface,
# scale the valid area into the requested texture instead of copying only half
# and sampling undefined/cleared columns. This is the failure visible in the
# PCSA00029 log: requested=1440x408 cached=720x408.
surface = src / "vita3k" / "renderer" / "src" / "vulkan" / "surface_cache.cpp"
s = surface.read_text()
old = """        if (bytes_per_pixel_requested == bytes_per_pixel_in_store) {
            const uint32_t copy_width = std::min(width, info.width - start_x);
            const uint32_t copy_height = std::min(height, info.height - start_sourced_line);
            vk::ImageCopy image_copy{
                .srcSubresource = vkutil::color_subresource_layer,
                .srcOffset = { static_cast<int32_t>(start_x), static_cast<int32_t>(start_sourced_line), 0 },
                .dstSubresource = vkutil::color_subresource_layer,
                .dstOffset = { 0,
                    0,
                    0 },
                .extent = {
                    // Copy only the part that the guest actually rendered.
                    copy_width,
                    copy_height,
                    1 }
            };
            cmd_buffer.copyImage(info.texture.image, vk::ImageLayout::eGeneral, casted->texture.image, vk::ImageLayout::eTransferDstOptimal, image_copy);
        } else {
"""
new = """        if (bytes_per_pixel_requested == bytes_per_pixel_in_store) {
            const uint32_t copy_width = std::min(width, info.width - start_x);
            const uint32_t copy_height = std::min(height, info.height - start_sourced_line);
            vk::ImageCopy image_copy{
                .srcSubresource = vkutil::color_subresource_layer,
                .srcOffset = { static_cast<int32_t>(start_x), static_cast<int32_t>(start_sourced_line), 0 },
                .dstSubresource = vkutil::color_subresource_layer,
                .dstOffset = { 0,
                    0,
                    0 },
                .extent = {
                    // Copy only the part that the guest actually rendered.
                    copy_width,
                    copy_height,
                    1 }
            };
            cmd_buffer.copyImage(info.texture.image, vk::ImageLayout::eGeneral, casted->texture.image, vk::ImageLayout::eTransferDstOptimal, image_copy);
        } else {
"""
if old not in s:
    raise SystemExit("partial surface copy anchor not found")
s = s.replace(old, new, 1)
old = "        casted->texture.transition_to(cmd_buffer, vkutil::ImageLayout::ColorAttachmentReadWrite);"
new = "        casted->texture.transition_to(cmd_buffer, vkutil::ImageLayout::SampledImage);"
if old not in s:
    raise SystemExit("casted texture final layout anchor not found")
s = s.replace(old, new, 1)
surface.write_text(s)

# Tsubomi currently rejects every "partial" typeless surface before reaching its
# byte-reinterpretation path. Uncharted legitimately views a 720px x 8-byte row
# as 1440px x 4-byte texels: both are exactly 5760 bytes. Allow that case when
# the requested byte range is fully covered by the cached render target.
s = surface.read_text()
old = """    // The typeless conversion path uses a row-strided transition buffer and
    // cannot safely synthesize texels outside the cached surface.
    if (partial_surface && bytes_per_pixel_requested != bytes_per_pixel_in_store)
        return std::nullopt;
"""
new = """    // Pixel widths can differ for a legitimate typeless reinterpretation.
    // Example from Uncharted: 720 x 8-byte texels == 1440 x 4-byte texels.
    // Judge coverage in bytes before falling back to the ordinary texture cache.
    const uint64_t requested_byte_end =
        static_cast<uint64_t>(start_x) * bytes_per_pixel_requested
        + static_cast<uint64_t>(width) * bytes_per_pixel_requested;
    const uint64_t stored_pixel_bytes =
        static_cast<uint64_t>(info.width) * bytes_per_pixel_in_store;
    const bool typeless_byte_covered =
        bytes_per_pixel_requested != bytes_per_pixel_in_store
        && static_cast<uint64_t>(start_sourced_line) + height <= info.height
        && requested_byte_end <= stored_pixel_bytes;

    if (partial_surface && bytes_per_pixel_requested != bytes_per_pixel_in_store && !typeless_byte_covered)
        return std::nullopt;

    if (partial_surface && typeless_byte_covered) {
        LOG_INFO_ONCE("Using byte-covered typeless surface cast: requested={}x{} bpp={} cached={}x{} bpp={} rowBytes={}",
            width, height, bytes_per_pixel_requested, info.width, info.height,
            bytes_per_pixel_in_store, stored_pixel_bytes);
    }
"""
if old not in s:
    raise SystemExit("typeless partial guard anchor not found")
s = s.replace(old, new, 1)
surface.write_text(s)

# Match the real ABI layout closely enough to store/retrieve the clip rectangle.
types = src / "vita3k" / "renderer" / "include" / "renderer" / "gxm_types.h"
s = types.read_text()
old = """    struct {
        uint32_t disabled : 1;
        uint32_t downscale : 1;
        uint32_t gamma : 2;
        uint32_t : 28;
    };
    uint32_t width;
    uint32_t height;
    uint32_t strideInPixels;
    Ptr<void> data;
    SceGxmColorFormat colorFormat;
    SceGxmColorSurfaceType surfaceType;
    // opaque end
"""
new = """    struct {
        uint32_t disabled : 1;
        uint32_t downscale : 1;
        uint32_t gamma : 2;
        uint32_t clip_x_min : 12;
        uint32_t clip_y_min : 12;
        uint32_t : 4;
    };
    uint16_t width;
    uint16_t height;
    uint32_t strideInPixels;
    Ptr<void> data;
    SceGxmColorFormat colorFormat;
    SceGxmColorSurfaceType surfaceType;
    uint32_t clip_x_max : 12;
    uint32_t clip_y_max : 12;
    uint32_t : 8;
    // opaque end
"""
if old not in s:
    raise SystemExit("SceGxmColorSurface layout anchor not found")
s = s.replace(old, new, 1)
types.write_text(s)

gxm = src / "vita3k" / "modules" / "SceGxm" / "SceGxm.cpp"
s = gxm.read_text()
old = """EXPORT(void, sceGxmColorSurfaceGetClip, const SceGxmColorSurface *surface, uint32_t *xMin, uint32_t *yMin, uint32_t *xMax, uint32_t *yMax) {
    TRACY_FUNC(sceGxmColorSurfaceGetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    UNIMPLEMENTED();
}
"""
new = """EXPORT(void, sceGxmColorSurfaceGetClip, const SceGxmColorSurface *surface, uint32_t *xMin, uint32_t *yMin, uint32_t *xMax, uint32_t *yMax) {
    TRACY_FUNC(sceGxmColorSurfaceGetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    if (xMin)
        *xMin = surface->clip_x_min;
    if (yMin)
        *yMin = surface->clip_y_min;
    if (xMax)
        *xMax = surface->clip_x_max;
    if (yMax)
        *yMax = surface->clip_y_max;
}
"""
if old not in s:
    raise SystemExit("ColorSurfaceGetClip anchor not found")
s = s.replace(old, new, 1)

old = """    surface->downscale = scaleMode == SCE_GXM_COLOR_SURFACE_SCALE_MSAA_DOWNSCALE;
    surface->width = width;
    surface->height = height;
    surface->strideInPixels = strideInPixels;
"""
new = """    surface->downscale = scaleMode == SCE_GXM_COLOR_SURFACE_SCALE_MSAA_DOWNSCALE;
    surface->width = static_cast<uint16_t>(width);
    surface->height = static_cast<uint16_t>(height);
    surface->clip_x_max = width - 1;
    surface->clip_y_max = height - 1;
    surface->strideInPixels = strideInPixels;
"""
if old not in s:
    raise SystemExit("ColorSurfaceInit anchor not found")
s = s.replace(old, new, 1)

old = """EXPORT(void, sceGxmColorSurfaceSetClip, SceGxmColorSurface *surface, uint32_t xMin, uint32_t yMin, uint32_t xMax, uint32_t yMax) {
    TRACY_FUNC(sceGxmColorSurfaceSetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    UNIMPLEMENTED();
}
"""
new = """EXPORT(void, sceGxmColorSurfaceSetClip, SceGxmColorSurface *surface, uint32_t xMin, uint32_t yMin, uint32_t xMax, uint32_t yMax) {
    TRACY_FUNC(sceGxmColorSurfaceSetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    surface->clip_x_min = xMin;
    surface->clip_y_min = yMin;
    surface->clip_x_max = xMax;
    surface->clip_y_max = yMax;
}
"""
if old not in s:
    raise SystemExit("ColorSurfaceSetClip anchor not found")
s = s.replace(old, new, 1)

for axis in ("U", "V"):
    prefix = f"""EXPORT(int, sceGxmTextureSet{axis}AddrModeSafe, SceGxmTexture *texture, SceGxmTextureAddrMode mode) {{
    TRACY_FUNC(sceGxmTextureSet{axis}AddrModeSafe, texture, mode);
    if (!texture)
        return RET_ERROR(SCE_GXM_ERROR_INVALID_POINTER);

"""
    idx = s.find(prefix)
    if idx == -1:
        raise SystemExit(f"safe {axis} addr-mode prefix not found")
    tail = s[idx + len(prefix):]
    member = axis.lower() + "addr_mode"
    body_old = f"""    if (!verify_texture_mode(texture, mode))
        return RET_ERROR(SCE_GXM_ERROR_UNSUPPORTED);

    texture->{member} = mode;
    return 0;
"""
    body_new = f"""    if (!verify_texture_mode(texture, mode)) {{
        if ((texture->type << 29) == SCE_GXM_TEXTURE_CUBE || (texture->type << 29) == SCE_GXM_TEXTURE_CUBE_ARBITRARY) {{
            LOG_WARN_ONCE("Cube texture {axis} addr mode {{}} unsupported - coercing to CLAMP", fmt::underlying(mode));
            texture->{member} = SCE_GXM_TEXTURE_ADDR_CLAMP;
            return 0;
        }}
        return RET_ERROR(SCE_GXM_ERROR_UNSUPPORTED);
    }}

    texture->{member} = mode;
    return 0;
"""
    if not tail.startswith(body_old):
        raise SystemExit(f"safe {axis} addr-mode body anchor not found")
    s = s[:idx + len(prefix)] + body_new + tail[len(body_old):]

gxm.write_text(s)
print("VitaJoN Uncharted graphics compatibility patches applied")
PY


# Vita3K+ renderer/shader fixes selected for the corruption observed on Apple/MoltenVK.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
src = Path(sys.argv[1])

surface = src / "vita3k" / "renderer" / "src" / "vulkan" / "surface_cache.cpp"
s = surface.read_text()

# Vita3K+ 1a081a: preserve unsigned bit patterns when a floating-point store is
# reinterpreted through an integer/normalized texture view.
old = """            casted->texture.width = width;
            casted->texture.height = height;
            casted->texture.format = vk_format;

            // find the swizzle we need to apply
"""
new = """            casted->texture.width = width;
            casted->texture.height = height;

            auto store_is_f16 = [](SceGxmColorBaseFormat f) {
                return f == SCE_GXM_COLOR_BASE_FORMAT_F16
                    || f == SCE_GXM_COLOR_BASE_FORMAT_F16F16
                    || f == SCE_GXM_COLOR_BASE_FORMAT_F16F16F16F16;
            };

            auto force_unsigned_reinterpret_format = [](vk::Format fmt) {
                switch (fmt) {
                case vk::Format::eR8Snorm: return vk::Format::eR8Unorm;
                case vk::Format::eR8G8Snorm: return vk::Format::eR8G8Unorm;
                case vk::Format::eR8G8B8A8Snorm: return vk::Format::eR8G8B8A8Unorm;
                case vk::Format::eR16Snorm: return vk::Format::eR16Unorm;
                case vk::Format::eR16G16Snorm: return vk::Format::eR16G16Unorm;
                case vk::Format::eR16G16B16A16Snorm: return vk::Format::eR16G16B16A16Unorm;
                case vk::Format::eR8Sint: return vk::Format::eR8Uint;
                case vk::Format::eR8G8Sint: return vk::Format::eR8G8Uint;
                case vk::Format::eR8G8B8A8Sint: return vk::Format::eR8G8B8A8Uint;
                default: return fmt;
                }
            };

            casted->texture.format = (bytes_per_pixel_requested != bytes_per_pixel_in_store && store_is_f16(info.format))
                ? force_unsigned_reinterpret_format(vk_format)
                : vk_format;

            // find the swizzle we need to apply
"""
if old not in s:
    raise SystemExit("casted texture format anchor not found")
s = s.replace(old, new, 1)

# The old Tsubomi path copied a freshly-written Vulkan image into a buffer and
# immediately consumed that buffer as transfer source, without making either
# dependency explicit. On Apple/MoltenVK this can expose stale/partially-written
# words. Port the synchronization used by later Vita3K+.
old = """            // copy the image to the buffer
            const uint32_t src_pixel_stride = static_cast<uint32_t>((info.stride_bytes / bytes_per_pixel_in_store) * state.res_multiplier);
            vk::BufferImageCopy copy_image_buffer{
                .bufferOffset = 0,
                .bufferRowLength = src_pixel_stride,
                .bufferImageHeight = height,
                .imageSubresource = vkutil::color_subresource_layer,
                .imageOffset = { 0,
                    static_cast<int32_t>(start_sourced_line),
                    0 },
                .imageExtent = { info.width, height, 1 }
            };
            cmd_buffer.copyImageToBuffer(info.texture.image, vk::ImageLayout::eGeneral, casted->transition_buffer.buffer, copy_image_buffer);

            // then the buffer to the image
            const uint32_t dst_pixel_stride = (stride_bytes / bytes_per_pixel_requested) * state.res_multiplier;
"""
new = """            // copy the image to the buffer
            const uint32_t src_pixel_stride = static_cast<uint32_t>((info.stride_bytes / bytes_per_pixel_in_store) * state.res_multiplier);
            vk::BufferImageCopy copy_image_buffer{
                .bufferOffset = 0,
                .bufferRowLength = src_pixel_stride,
                .bufferImageHeight = height,
                .imageSubresource = vkutil::color_subresource_layer,
                .imageOffset = { 0,
                    static_cast<int32_t>(start_sourced_line),
                    0 },
                .imageExtent = { info.width, height, 1 }
            };

            vk::ImageMemoryBarrier image_to_transfer{
                .srcAccessMask = vk::AccessFlagBits::eColorAttachmentWrite | vk::AccessFlagBits::eShaderWrite,
                .dstAccessMask = vk::AccessFlagBits::eTransferRead,
                .oldLayout = vk::ImageLayout::eGeneral,
                .newLayout = vk::ImageLayout::eGeneral,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .image = info.texture.image,
                .subresourceRange = vkutil::color_subresource_range
            };
            cmd_buffer.pipelineBarrier(
                vk::PipelineStageFlagBits::eColorAttachmentOutput | vk::PipelineStageFlagBits::eFragmentShader,
                vk::PipelineStageFlagBits::eTransfer, {}, {}, {}, image_to_transfer);

            cmd_buffer.copyImageToBuffer(info.texture.image, vk::ImageLayout::eGeneral, casted->transition_buffer.buffer, copy_image_buffer);

            vk::BufferMemoryBarrier transfer_write_to_read{
                .srcAccessMask = vk::AccessFlagBits::eTransferWrite,
                .dstAccessMask = vk::AccessFlagBits::eTransferRead,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .buffer = casted->transition_buffer.buffer,
                .offset = 0,
                .size = VK_WHOLE_SIZE
            };
            cmd_buffer.pipelineBarrier(
                vk::PipelineStageFlagBits::eTransfer,
                vk::PipelineStageFlagBits::eTransfer, {}, {}, transfer_write_to_read, {});

            LOG_INFO_ONCE("VitaJoN typeless transfer barriers active: image->buffer->image synchronized");

            // then the buffer to the image
            const uint32_t dst_pixel_stride = (stride_bytes / bytes_per_pixel_requested) * state.res_multiplier;
"""
if old not in s:
    raise SystemExit("typeless transfer block anchor not found")
s = s.replace(old, new, 1)
surface.write_text(s)

# Vita3K+ 1a081a: private register banks must start at zero. Undefined private
# registers can manifest as random colour/speckle corruption.
spirv = src / "vita3k" / "shader" / "src" / "spirv_recompiler.cpp"
s = spirv.read_text()
old = """    // Create register banks
    spv_params.ins = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, pa_arr_type, "pa");
    spv_params.uniforms = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, sa_arr_type, "sa");
    spv_params.internals = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, i_arr_type, "internals");
    spv_params.temps = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, temp_arr_type, "r");
    spv_params.predicates = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, pred_arr_type, "p");
    spv_params.indexes = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, index_arr_type, "idx");
    spv_params.outs = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, o_arr_type, "outs");
"""
new = """    // Create register banks. Vita hardware starts these predictably; leaving
    // SPIR-V Private storage undefined creates device-dependent garbage.
    auto make_zeroed_bank = [&](spv::Id arr_type, const char *name) {
        return b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, arr_type, name, b.makeNullConstant(arr_type));
    };

    spv_params.ins = make_zeroed_bank(pa_arr_type, "pa");
    spv_params.uniforms = make_zeroed_bank(sa_arr_type, "sa");
    spv_params.internals = make_zeroed_bank(i_arr_type, "internals");
    spv_params.temps = make_zeroed_bank(temp_arr_type, "r");
    spv_params.predicates = make_zeroed_bank(pred_arr_type, "p");
    spv_params.indexes = make_zeroed_bank(index_arr_type, "idx");
    spv_params.outs = make_zeroed_bank(o_arr_type, "outs");
"""
if old not in s:
    raise SystemExit("SPIR-V register-bank anchor not found")
s = s.replace(old, new, 1)
spirv.write_text(s)

# Vita3K+ 6cd1cb: scalar DUAL operations replicate their result to all masked
# destination components on real hardware. Missing the broadcast is known to
# break Uncharted eye/material rendering and can poison later calculations.
alu = src / "vita3k" / "shader" / "src" / "translator" / "alu.cpp"
s = alu.read_text()
old = """        disasm_str += fmt::format("{} {}", disasm::opcode_str(code), disasm::operand_to_str(dest, write_mask_dest));

        for (Operand &op : ops)
"""
new = """        if (result != spv::NoResult && m_b.getNumComponents(result) == 1) {
            result = postprocess_dot_result_for_store(m_b, result, write_mask_dest);
        }

        disasm_str += fmt::format("{} {}", disasm::opcode_str(code), disasm::operand_to_str(dest, write_mask_dest));

        for (Operand &op : ops)
"""
if old not in s:
    raise SystemExit("DUAL scalar broadcast anchor not found")
s = s.replace(old, new, 1)
alu.write_text(s)

# Force regeneration of cached shaders after changing translator semantics.
hdr = src / "vita3k" / "shader" / "include" / "shader" / "spirv_recompiler.h"
s = hdr.read_text()
old = "static constexpr uint32_t CURRENT_VERSION = 13;"
if old not in s:
    raise SystemExit("shader cache version anchor not found")
s = s.replace(old, "static constexpr uint32_t CURRENT_VERSION = 14;", 1)
hdr.write_text(s)

uniform = src / "vita3k" / "shader" / "include" / "shader" / "uniform_block.h"
s = uniform.read_text()
old = """struct RenderFragUniformBlock {
    float back_disabled;
    float front_disabled;
    float writing_mask;
    float use_raw_image;
    float res_multiplier;
};
"""
new = """struct RenderFragUniformBlock {
    float back_disabled = 0.0f;
    float front_disabled = 0.0f;
    float writing_mask = 0.0f;
    float use_raw_image = 0.0f;
    float res_multiplier = 1.0f;
};
"""
if old not in s:
    raise SystemExit("fragment uniform defaults anchor not found")
s = s.replace(old, new, 1)
uniform.write_text(s)

print("VitaJoN Vita3K+ typeless synchronization and Uncharted shader fixes applied")
PY


# VitaJoN 0.47.6: replace Tsubomi's typeless buffer reinterpret with the
# Vita3K+ compute-deinterleave path. This is intentionally applied after the
# previous compatibility patches so it supersedes the old image->buffer->image
# reinterpret rather than layering another tweak on top of it.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])

hdr = src / "vita3k" / "renderer" / "include" / "renderer" / "vulkan" / "surface_cache.h"
s = hdr.read_text()

old = """struct CastedTexture {
    vkutil::Image texture;
    // only used if an image to image copy is not possible
    vkutil::Buffer transition_buffer;
    uint64_t scene_timestamp = 0;
"""
new = """struct CastedTexture {
    vkutil::Image texture;
    // only used if an image to image copy is not possible
    vkutil::Buffer transition_buffer;
    // compute-deinterleaved output used by typeless 64->32 bit reinterpretation
    vkutil::Buffer reinterpret_buffer;
    uint64_t scene_timestamp = 0;
"""
if old not in s:
    raise SystemExit("CastedTexture anchor not found")
s = s.replace(old, new, 1)

old = """struct SurfaceRetrieveResult {
    vk::ImageView view;
    vkutil::Image *base_image;
};

class VKSurfaceCache {
"""
new = """struct SurfaceRetrieveResult {
    vk::ImageView view;
    vkutil::Image *base_image;
};

struct ReinterpretPushConstants {
    uint32_t out_width;
    uint32_t out_height;
    uint32_t scaled_store_w;
    uint32_t scaled_store_h;
    uint32_t ratio;
    uint32_t half_index;
    uint32_t interleave;
};

class VKSurfaceCache {
"""
if old not in s:
    raise SystemExit("ReinterpretPushConstants anchor not found")
s = s.replace(old, new, 1)

old = """    void destroy_surface(ColorSurfaceCacheInfo &info);
    void destroy_surface(DepthStencilSurfaceCacheInfo &info);
    vk::ImageView retrieve_sampled_view(ColorSurfaceCacheInfo &info, vk::Format format,
        const vk::ComponentMapping &components);

public:
"""
new = """    void destroy_surface(ColorSurfaceCacheInfo &info);
    void destroy_surface(DepthStencilSurfaceCacheInfo &info);
    vk::ImageView retrieve_sampled_view(ColorSurfaceCacheInfo &info, vk::Format format,
        const vk::ComponentMapping &components);

    vk::ShaderModule reinterpret_shader = nullptr;
    vk::DescriptorSetLayout reinterpret_desc_layout = nullptr;
    vk::PipelineLayout reinterpret_pipeline_layout = nullptr;
    vk::Pipeline reinterpret_pipeline = nullptr;
    vk::DescriptorPool reinterpret_desc_pool = nullptr;
    std::vector<vk::DescriptorSet> reinterpret_desc_sets;
    uint32_t reinterpret_desc_idx = 0;
    void ensure_reinterpret_pipeline();

public:
"""
if old not in s:
    raise SystemExit("reinterpret pipeline member anchor not found")
s = s.replace(old, new, 1)
hdr.write_text(s)

surface = src / "vita3k" / "renderer" / "src" / "vulkan" / "surface_cache.cpp"
s = surface.read_text()

# Destroy the new buffer with each casted texture.
old = """    for (auto &casted : info.casted_textures) {
        destroy_queue.add_buffer(casted.transition_buffer);
        destroy_queue.add_image(casted.texture);
    }
"""
new = """    for (auto &casted : info.casted_textures) {
        destroy_queue.add_buffer(casted.transition_buffer);
        destroy_queue.add_buffer(casted.reinterpret_buffer);
        destroy_queue.add_image(casted.texture);
    }
"""
if s.count(old) < 1:
    raise SystemExit("destroy_surface casted anchor not found")
s = s.replace(old, new, 1)

old = """        for (auto &casted : info.casted_textures) {
            casted.transition_buffer.destroy();
            casted.texture.destroy();
        }
"""
new = """        for (auto &casted : info.casted_textures) {
            casted.transition_buffer.destroy();
            casted.reinterpret_buffer.destroy();
            casted.texture.destroy();
        }
"""
if old not in s:
    raise SystemExit("cleanup casted anchor not found")
s = s.replace(old, new, 1)

# Destroy the global compute objects during renderer cleanup.
anchor = """    color_address_lookup.clear();
    depth_address_lookup.clear();
    stencil_address_lookup.clear();
"""
insert = """    if (reinterpret_pipeline) {
        state.device.destroy(reinterpret_pipeline);
        state.device.destroy(reinterpret_pipeline_layout);
        state.device.destroy(reinterpret_desc_layout);
        state.device.destroy(reinterpret_desc_pool);
        state.device.destroy(reinterpret_shader);
        reinterpret_pipeline = nullptr;
        reinterpret_desc_sets.clear();
    }

    color_address_lookup.clear();
    depth_address_lookup.clear();
    stencil_address_lookup.clear();
"""
if anchor not in s:
    raise SystemExit("cleanup pipeline anchor not found")
s = s.replace(anchor, insert, 1)

# Replace only the typeless branch inside retrieve_color_surface_as_texture.
start_marker = '''        } else {
            LOG_INFO_ONCE("Game is doing typeless copies");
'''
end_marker = '''        }
        casted->texture.transition_to(cmd_buffer, vkutil::ImageLayout::SampledImage);
'''
start = s.find(start_marker)
if start == -1:
    raise SystemExit("typeless branch start not found")
end = s.find(end_marker, start)
if end == -1:
    raise SystemExit("typeless branch end not found")

new_branch = '''        } else {
            LOG_INFO_ONCE("Game is doing typeless copies via VitaJoN compute deinterleave");

            const uint32_t ratio = bytes_per_pixel_in_store / bytes_per_pixel_requested;
            if (ratio == 0 || (bytes_per_pixel_in_store % bytes_per_pixel_requested) != 0)
                return std::nullopt;

            const uint32_t native_byte_offset = data_delta % stride_bytes;
            const uint32_t sub_texel_byte = native_byte_offset % bytes_per_pixel_in_store;
            const uint32_t native_store_col = native_byte_offset / bytes_per_pixel_in_store;
            const uint32_t src_pixel_stride = static_cast<uint32_t>((info.stride_bytes / bytes_per_pixel_in_store) * state.res_multiplier);
            const uint32_t half_index = sub_texel_byte / bytes_per_pixel_requested;

            const bool full_row_reinterpret =
                native_store_col == 0
                && start_sourced_line == 0
                && width == ratio * src_pixel_stride
                && height <= info.height;

            if (full_row_reinterpret) {
                ensure_reinterpret_pipeline();

                const vk::DeviceSize src_size =
                    static_cast<vk::DeviceSize>(src_pixel_stride) * bytes_per_pixel_in_store * align(height, 4)
                    + bytes_per_pixel_in_store;
                const vk::DeviceSize dst_size =
                    static_cast<vk::DeviceSize>(width) * bytes_per_pixel_requested * align(height, 4)
                    + bytes_per_pixel_requested;

                if (!casted->transition_buffer.buffer || casted->transition_buffer.size < src_size) {
                    state.frame().destroy_queue.add_buffer(casted->transition_buffer);
                    casted->transition_buffer = vkutil::Buffer(src_size);
                    casted->transition_buffer.init_buffer(vk::BufferUsageFlagBits::eTransferDst | vk::BufferUsageFlagBits::eStorageBuffer);
                }
                if (!casted->reinterpret_buffer.buffer || casted->reinterpret_buffer.size < dst_size) {
                    state.frame().destroy_queue.add_buffer(casted->reinterpret_buffer);
                    casted->reinterpret_buffer = vkutil::Buffer(dst_size);
                    casted->reinterpret_buffer.init_buffer(vk::BufferUsageFlagBits::eTransferSrc | vk::BufferUsageFlagBits::eStorageBuffer);
                }

                vk::ImageMemoryBarrier pre_dump{
                    .srcAccessMask = vk::AccessFlagBits::eColorAttachmentWrite | vk::AccessFlagBits::eShaderWrite,
                    .dstAccessMask = vk::AccessFlagBits::eTransferRead,
                    .oldLayout = vk::ImageLayout::eGeneral,
                    .newLayout = vk::ImageLayout::eGeneral,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .image = info.texture.image,
                    .subresourceRange = vkutil::color_subresource_range
                };
                cmd_buffer.pipelineBarrier(
                    vk::PipelineStageFlagBits::eColorAttachmentOutput | vk::PipelineStageFlagBits::eFragmentShader,
                    vk::PipelineStageFlagBits::eTransfer, {}, {}, {}, pre_dump);

                vk::BufferImageCopy dump{
                    .bufferOffset = 0,
                    .bufferRowLength = src_pixel_stride,
                    .bufferImageHeight = height,
                    .imageSubresource = vkutil::color_subresource_layer,
                    .imageOffset = { 0, 0, 0 },
                    .imageExtent = { info.width, height, 1 }
                };
                cmd_buffer.copyImageToBuffer(
                    info.texture.image, vk::ImageLayout::eGeneral,
                    casted->transition_buffer.buffer, dump);

                vk::BufferMemoryBarrier to_compute{
                    .srcAccessMask = vk::AccessFlagBits::eTransferWrite,
                    .dstAccessMask = vk::AccessFlagBits::eShaderRead,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .buffer = casted->transition_buffer.buffer,
                    .offset = 0,
                    .size = VK_WHOLE_SIZE
                };
                cmd_buffer.pipelineBarrier(
                    vk::PipelineStageFlagBits::eTransfer,
                    vk::PipelineStageFlagBits::eComputeShader, {}, {}, to_compute, {});

                vk::DescriptorSet dset = reinterpret_desc_sets[reinterpret_desc_idx];
                reinterpret_desc_idx = (reinterpret_desc_idx + 1) % static_cast<uint32_t>(reinterpret_desc_sets.size());

                vk::DescriptorBufferInfo src_bi{ casted->transition_buffer.buffer, 0, VK_WHOLE_SIZE };
                vk::DescriptorBufferInfo dst_bi{ casted->reinterpret_buffer.buffer, 0, VK_WHOLE_SIZE };
                std::array<vk::WriteDescriptorSet, 2> writes;
                writes[0] = vk::WriteDescriptorSet{
                    .dstSet = dset, .dstBinding = 0, .dstArrayElement = 0,
                    .descriptorType = vk::DescriptorType::eStorageBuffer
                };
                writes[0].setBufferInfo(src_bi);
                writes[1] = vk::WriteDescriptorSet{
                    .dstSet = dset, .dstBinding = 1, .dstArrayElement = 0,
                    .descriptorType = vk::DescriptorType::eStorageBuffer
                };
                writes[1].setBufferInfo(dst_bi);
                state.device.updateDescriptorSets(writes, {});

                ReinterpretPushConstants pc{
                    .out_width = width,
                    .out_height = height,
                    .scaled_store_w = src_pixel_stride,
                    .scaled_store_h = height,
                    .ratio = ratio,
                    .half_index = half_index,
                    .interleave = 0u
                };

                cmd_buffer.bindPipeline(vk::PipelineBindPoint::eCompute, reinterpret_pipeline);
                cmd_buffer.bindDescriptorSets(
                    vk::PipelineBindPoint::eCompute, reinterpret_pipeline_layout, 0, dset, {});
                cmd_buffer.pushConstants(
                    reinterpret_pipeline_layout, vk::ShaderStageFlagBits::eCompute,
                    0, sizeof(pc), &pc);
                cmd_buffer.dispatch((width + 7u) / 8u, (height + 7u) / 8u, 1);

                vk::BufferMemoryBarrier to_copy{
                    .srcAccessMask = vk::AccessFlagBits::eShaderWrite,
                    .dstAccessMask = vk::AccessFlagBits::eTransferRead,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .buffer = casted->reinterpret_buffer.buffer,
                    .offset = 0,
                    .size = VK_WHOLE_SIZE
                };
                cmd_buffer.pipelineBarrier(
                    vk::PipelineStageFlagBits::eComputeShader,
                    vk::PipelineStageFlagBits::eTransfer, {}, {}, to_copy, {});

                vk::BufferImageCopy to_image{
                    .bufferOffset = 0,
                    .bufferRowLength = width,
                    .bufferImageHeight = height,
                    .imageSubresource = vkutil::color_subresource_layer,
                    .imageOffset = { 0, 0, 0 },
                    .imageExtent = { width, height, 1 }
                };
                cmd_buffer.copyBufferToImage(
                    casted->reinterpret_buffer.buffer, casted->texture.image,
                    vk::ImageLayout::eTransferDstOptimal, to_image);

                LOG_INFO_ONCE("VitaJoN compute typeless path active: {}x{} store={} ratio={} interleave=0",
                    width, height, src_pixel_stride, ratio);
            } else {
                // Keep the corrected direct-byte path only for genuine cropped/offset reads.
                const uint32_t scaled_store_col =
                    static_cast<uint32_t>((native_byte_offset / bytes_per_pixel_in_store) * state.res_multiplier);
                const uint32_t src_byte_offset =
                    scaled_store_col * bytes_per_pixel_in_store + sub_texel_byte;
                const uint32_t dst_pixel_stride = src_pixel_stride * ratio;
                const vk::DeviceSize buffer_size =
                    static_cast<vk::DeviceSize>(src_pixel_stride) * bytes_per_pixel_in_store * align(height, 4)
                    + src_byte_offset + bytes_per_pixel_in_store;

                if (!casted->transition_buffer.buffer || casted->transition_buffer.size < buffer_size) {
                    state.frame().destroy_queue.add_buffer(casted->transition_buffer);
                    casted->transition_buffer = vkutil::Buffer(buffer_size);
                    casted->transition_buffer.init_buffer(
                        vk::BufferUsageFlagBits::eTransferDst | vk::BufferUsageFlagBits::eTransferSrc);
                }

                vk::BufferImageCopy copy{
                    .bufferOffset = 0,
                    .bufferRowLength = src_pixel_stride,
                    .bufferImageHeight = height,
                    .imageSubresource = vkutil::color_subresource_layer,
                    .imageOffset = { 0, static_cast<int32_t>(start_sourced_line), 0 },
                    .imageExtent = { info.width, height, 1 }
                };

                vk::ImageMemoryBarrier img_barrier{
                    .srcAccessMask = vk::AccessFlagBits::eColorAttachmentWrite | vk::AccessFlagBits::eShaderWrite,
                    .dstAccessMask = vk::AccessFlagBits::eTransferRead,
                    .oldLayout = vk::ImageLayout::eGeneral,
                    .newLayout = vk::ImageLayout::eGeneral,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .image = info.texture.image,
                    .subresourceRange = vkutil::color_subresource_range
                };
                cmd_buffer.pipelineBarrier(
                    vk::PipelineStageFlagBits::eColorAttachmentOutput | vk::PipelineStageFlagBits::eFragmentShader,
                    vk::PipelineStageFlagBits::eTransfer, {}, {}, {}, img_barrier);
                cmd_buffer.copyImageToBuffer(
                    info.texture.image, vk::ImageLayout::eGeneral,
                    casted->transition_buffer.buffer, copy);

                vk::BufferMemoryBarrier buf_barrier{
                    .srcAccessMask = vk::AccessFlagBits::eTransferWrite,
                    .dstAccessMask = vk::AccessFlagBits::eTransferRead,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .buffer = casted->transition_buffer.buffer,
                    .offset = 0,
                    .size = VK_WHOLE_SIZE
                };
                cmd_buffer.pipelineBarrier(
                    vk::PipelineStageFlagBits::eTransfer,
                    vk::PipelineStageFlagBits::eTransfer, {}, {}, buf_barrier, {});

                copy.setBufferOffset(src_byte_offset)
                    .setBufferRowLength(dst_pixel_stride)
                    .setImageOffset({ 0, 0, 0 })
                    .setImageExtent({ width, height, 1 });
                cmd_buffer.copyBufferToImage(
                    casted->transition_buffer.buffer, casted->texture.image,
                    vk::ImageLayout::eTransferDstOptimal, copy);
            }
'''
s = s[:start] + new_branch + s[end:]
surface.write_text(s)

# Add the compute-pipeline constructor at the end of surface_cache.cpp.
s = surface.read_text()
ns = "} // namespace renderer::vulkan"
if ns not in s:
    raise SystemExit("surface_cache namespace end not found")

impl = r'''
void VKSurfaceCache::ensure_reinterpret_pipeline() {
    if (reinterpret_pipeline)
        return;

    const fs::path shader_path =
        state.static_assets / "shaders-builtin/vulkan" / "surface_cast_reinterpret.comp.spv";
    reinterpret_shader = vkutil::load_shader(state.device, shader_path);

    std::array<vk::DescriptorSetLayoutBinding, 2> bindings{};
    for (uint32_t i = 0; i < 2; ++i) {
        bindings[i] = vk::DescriptorSetLayoutBinding{
            .binding = i,
            .descriptorType = vk::DescriptorType::eStorageBuffer,
            .descriptorCount = 1,
            .stageFlags = vk::ShaderStageFlagBits::eCompute
        };
    }

    vk::DescriptorSetLayoutCreateInfo layout_info{};
    layout_info.setBindings(bindings);
    reinterpret_desc_layout = state.device.createDescriptorSetLayout(layout_info);

    vk::PushConstantRange push_range{
        .stageFlags = vk::ShaderStageFlagBits::eCompute,
        .offset = 0,
        .size = sizeof(ReinterpretPushConstants)
    };
    vk::PipelineLayoutCreateInfo pl_info{};
    pl_info.setSetLayouts(reinterpret_desc_layout);
    pl_info.setPushConstantRanges(push_range);
    reinterpret_pipeline_layout = state.device.createPipelineLayout(pl_info);

    vk::PipelineShaderStageCreateInfo stage{
        .stage = vk::ShaderStageFlagBits::eCompute,
        .module = reinterpret_shader,
        .pName = "main"
    };
    vk::ComputePipelineCreateInfo pipeline_info{
        .stage = stage,
        .layout = reinterpret_pipeline_layout
    };
    reinterpret_pipeline = state.device.createComputePipeline(nullptr, pipeline_info).value;

    constexpr uint32_t NB_SETS = 256;
    vk::DescriptorPoolSize pool_size{
        vk::DescriptorType::eStorageBuffer, 2 * NB_SETS
    };
    vk::DescriptorPoolCreateInfo pool_info{ .maxSets = NB_SETS };
    pool_info.setPoolSizes(pool_size);
    reinterpret_desc_pool = state.device.createDescriptorPool(pool_info);

    std::vector<vk::DescriptorSetLayout> layouts(NB_SETS, reinterpret_desc_layout);
    vk::DescriptorSetAllocateInfo alloc_info{ .descriptorPool = reinterpret_desc_pool };
    alloc_info.setSetLayouts(layouts);
    reinterpret_desc_sets = state.device.allocateDescriptorSets(alloc_info);
    reinterpret_desc_idx = 0;

    LOG_INFO("VitaJoN typeless compute pipeline created");
}

'''
s = s.replace(ns, impl + ns, 1)
surface.write_text(s)

shader = src / "vita3k" / "shaders-builtin" / "vulkan" / "surface_cast_reinterpret.comp"
shader.write_text(r'''#version 450

layout(local_size_x = 8, local_size_y = 8) in;

layout(push_constant) uniform PushConstants {
    uint out_width;
    uint out_height;
    uint scaled_store_w;
    uint scaled_store_h;
    uint ratio;
    uint half_index;
    uint interleave;
} pc;

layout(set = 0, binding = 0, std430) readonly buffer SrcBuffer { uint src[]; };
layout(set = 0, binding = 1, std430) writeonly buffer DstBuffer { uint dst[]; };

void main() {
    const uint x = gl_GlobalInvocationID.x;
    const uint y = gl_GlobalInvocationID.y;
    if (x >= pc.out_width || y >= pc.out_height)
        return;

    uint s = x / pc.ratio;
    if (s >= pc.scaled_store_w)
        s = pc.scaled_store_w - 1u;

    uint ys = y;
    if (ys >= pc.scaled_store_h)
        ys = pc.scaled_store_h - 1u;

    const uint src_row_words = pc.scaled_store_w * pc.ratio;
    const uint word_idx = (pc.interleave != 0u) ? (x % pc.ratio) : pc.half_index;
    dst[y * pc.out_width + x] =
        src[ys * src_row_words + s * pc.ratio + word_idx];
}
''')

print("VitaJoN 0.47.6 compute typeless renderer patch applied")
PY
