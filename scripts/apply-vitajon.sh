#!/usr/bin/env bash
set -euo pipefail

SRC="${1:-source}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

test -d "$SRC/ios"
cp "$ROOT/config/VitaJoN.entitlements" "$SRC/ios/VitaJoN.entitlements"


# VitaJoN 0.48.1: bring the pinned Tsubomi core up to the exact renderer/GXM
# fixes present in official Vita3K Android build 4098 (bbd5c362), before
# applying the iOS frontend adaptations below. These four commits are the
# graphics/runtime-relevant delta after the Tsubomi pin.
UPSTREAM_4098_COMMITS=(
  1861db65e7b13cd64604bcd68986b5bd9ba0a495
  85556014db0f2e157d8ded6127cb891015489203
  ecee68421c0a32eb4a5741d5df9b6cc461934a24
  bbd5c3624a06572fe4f16f67564f53a7540e1f42
)
for sha in "${UPSTREAM_4098_COMMITS[@]}"; do
  git -C "$SRC" fetch --quiet --no-tags https://github.com/Vita3K/Vita3K.git "$sha"
  git -C "$SRC" cherry-pick --no-commit "$sha"
done
git -C "$SRC" diff --check
echo "VitaJoN: official Android 4098 core delta applied"

python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])

info = src / "ios" / "Info.plist.in"
s = info.read_text()
s = s.replace("<string>Tsubomi</string>", "<string>VitaJoN</string>")
s = s.replace("<string>0.47.0</string>", "<string>0.48.3</string>", 1)
s = s.replace("<string>470</string>", "<string>483</string>", 1)
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

            LOG_INFO_ONCE("VitaJoN 0.48.0 Android-4098 direct typeless byte path active: requested={}x{} bpp={} cached={}x{} bpp={} stride={}",
                width, height, bytes_per_pixel_requested, info.width, info.height, bytes_per_pixel_in_store, stride_bytes);

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

# VitaJoN 0.48.0: match Vita3K+/4098 surface selection before the typeless cast.
# Uncharted reuses/overlaps color-surface address ranges with different formats and
# strides. Tsubomi previously tested only the nearest lower-address cache entry.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
surface = src / "vita3k" / "renderer" / "src" / "vulkan" / "surface_cache.cpp"
s = surface.read_text()

old = """    ColorSurfaceCacheInfo &info = *ite->second;

    if ((base_format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8 || info.format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8)
        && base_format != info.format)
        // don't even try to match u8u8u8 with something else
        return std::nullopt;

    if (tiling != info.tiling || info.stride_bytes != stride_bytes) {
        // if the tiling is different, also don't try to match them
        // about the strides, I've yet to see a case where the byte stride is different
        LOG_WARN_ONCE("Surface-as-texture miss (tiling/stride): texture=0x{:X} tiling={}/{} stride={}/{}",
            address, static_cast<int>(tiling), static_cast<int>(info.tiling), stride_bytes, info.stride_bytes);
        return std::nullopt;
    }
"""

new = """    // Vita3K+ Uncharted parity: several cached surfaces may overlap the same
    // guest address. Prefer an overlapping surface with the exact texture
    // tiling + byte stride instead of assuming the nearest lower address is it.
    if (tiling != ite->second->tiling || ite->second->stride_bytes != stride_bytes) {
        auto match = ite;
        bool found_layout_match = false;
        while (true) {
            if ((match->first + match->second->total_bytes) > address
                && match->second->tiling == tiling
                && match->second->stride_bytes == stride_bytes) {
                ite = match;
                found_layout_match = true;
                LOG_INFO_ONCE("VitaJoN 0.48.0 selected overlapping surface by stride/tiling: texture=0x{:X} surface=0x{:X} stride={}",
                    address, ite->first, stride_bytes);
                break;
            }
            if (match == color_address_lookup.begin())
                break;
            --match;
        }

        if (!found_layout_match) {
            LOG_WARN_ONCE("Surface-as-texture miss (tiling/stride): texture=0x{:X} requested tiling={} stride={}",
                address, static_cast<int>(tiling), stride_bytes);
            return std::nullopt;
        }
    }

    ColorSurfaceCacheInfo &info = *ite->second;

    if ((base_format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8 || info.format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8)
        && base_format != info.format)
        // don't even try to match u8u8u8 with something else
        return std::nullopt;
"""

if old not in s:
    raise SystemExit("VitaJoN 0.48.0 surface selection anchor not found")
s = s.replace(old, new, 1)
surface.write_text(s)

print("VitaJoN 0.48.0 Android-4098 typeless parity + overlap surface selection applied")
PY

# VitaJoN 0.48.1: remove experimental 476-480 renderer guesses that are NOT
# present in Android build 4098. Keep only iOS-specific synchronization and the
# byte-covered partial-typeless allowance required to reach the stock 4098
# 64-bit-render-target -> 32-bit-texture path under MoltenVK.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])

def must_replace(text, old, new, label, count=1):
    n = text.count(old)
    if n != count:
        raise SystemExit(f"{label}: expected {count}, found {n}")
    return text.replace(old, new, count)

# 1) Restore the exact SceGxmColorSurface representation used by official 4098.
types = src / "vita3k" / "renderer" / "include" / "renderer" / "gxm_types.h"
t = types.read_text()
custom_surface = """    struct {
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
stock_surface = """    struct {
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
t = must_replace(t, custom_surface, stock_surface, "restore SceGxmColorSurface")
types.write_text(t)

gxm = src / "vita3k" / "modules" / "SceGxm" / "SceGxm.cpp"
g = gxm.read_text()
custom_get_clip = """EXPORT(void, sceGxmColorSurfaceGetClip, const SceGxmColorSurface *surface, uint32_t *xMin, uint32_t *yMin, uint32_t *xMax, uint32_t *yMax) {
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
stock_get_clip = """EXPORT(void, sceGxmColorSurfaceGetClip, const SceGxmColorSurface *surface, uint32_t *xMin, uint32_t *yMin, uint32_t *xMax, uint32_t *yMax) {
    TRACY_FUNC(sceGxmColorSurfaceGetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    UNIMPLEMENTED();
}
"""
g = must_replace(g, custom_get_clip, stock_get_clip, "restore GetClip")

custom_init = """    surface->downscale = scaleMode == SCE_GXM_COLOR_SURFACE_SCALE_MSAA_DOWNSCALE;
    surface->width = static_cast<uint16_t>(width);
    surface->height = static_cast<uint16_t>(height);
    surface->clip_x_max = width - 1;
    surface->clip_y_max = height - 1;
    surface->strideInPixels = strideInPixels;
"""
stock_init = """    surface->downscale = scaleMode == SCE_GXM_COLOR_SURFACE_SCALE_MSAA_DOWNSCALE;
    surface->width = width;
    surface->height = height;
    surface->strideInPixels = strideInPixels;
"""
g = must_replace(g, custom_init, stock_init, "restore ColorSurfaceInit")

custom_set_clip = """EXPORT(void, sceGxmColorSurfaceSetClip, SceGxmColorSurface *surface, uint32_t xMin, uint32_t yMin, uint32_t xMax, uint32_t yMax) {
    TRACY_FUNC(sceGxmColorSurfaceSetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    surface->clip_x_min = xMin;
    surface->clip_y_min = yMin;
    surface->clip_x_max = xMax;
    surface->clip_y_max = yMax;
}
"""
stock_set_clip = """EXPORT(void, sceGxmColorSurfaceSetClip, SceGxmColorSurface *surface, uint32_t xMin, uint32_t yMin, uint32_t xMax, uint32_t yMax) {
    TRACY_FUNC(sceGxmColorSurfaceSetClip, surface, xMin, yMin, xMax, yMax);
    assert(surface);
    UNIMPLEMENTED();
}
"""
g = must_replace(g, custom_set_clip, stock_set_clip, "restore SetClip")

# 2) Android 4098 returns UNSUPPORTED for invalid cube address modes. Builds
# 476-480 coerced them to CLAMP, changing game-visible GXM behavior.
for axis in ("U", "V"):
    member = axis.lower() + "addr_mode"
    custom = f"""    if (!verify_texture_mode(texture, mode)) {{
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
    stock = f"""    if (!verify_texture_mode(texture, mode))
        return RET_ERROR(SCE_GXM_ERROR_UNSUPPORTED);

    texture->{member} = mode;
    return 0;
"""
    g = must_replace(g, custom, stock, f"restore cube {axis} mode")
gxm.write_text(g)

# 3) Restore official 4098 surface-cache semantics. The iOS-only transfer
# barriers are retained, but format selection, cache entry selection and final
# image layout must match the working Android core.
surface = src / "vita3k" / "renderer" / "src" / "vulkan" / "surface_cache.cpp"
v = surface.read_text()

custom_format = """            casted->texture.width = width;
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
stock_format = """            casted->texture.width = width;
            casted->texture.height = height;
            casted->texture.format = vk_format;

            // find the swizzle we need to apply
"""
v = must_replace(v, custom_format, stock_format, "restore cast format")

custom_select = """    // Vita3K+ Uncharted parity: several cached surfaces may overlap the same
    // guest address. Prefer an overlapping surface with the exact texture
    // tiling + byte stride instead of assuming the nearest lower address is it.
    if (tiling != ite->second->tiling || ite->second->stride_bytes != stride_bytes) {
        auto match = ite;
        bool found_layout_match = false;
        while (true) {
            if ((match->first + match->second->total_bytes) > address
                && match->second->tiling == tiling
                && match->second->stride_bytes == stride_bytes) {
                ite = match;
                found_layout_match = true;
                LOG_INFO_ONCE("VitaJoN 0.48.0 selected overlapping surface by stride/tiling: texture=0x{:X} surface=0x{:X} stride={}",
                    address, ite->first, stride_bytes);
                break;
            }
            if (match == color_address_lookup.begin())
                break;
            --match;
        }

        if (!found_layout_match) {
            LOG_WARN_ONCE("Surface-as-texture miss (tiling/stride): texture=0x{:X} requested tiling={} stride={}",
                address, static_cast<int>(tiling), stride_bytes);
            return std::nullopt;
        }
    }

    ColorSurfaceCacheInfo &info = *ite->second;

    if ((base_format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8 || info.format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8)
        && base_format != info.format)
        // don't even try to match u8u8u8 with something else
        return std::nullopt;
"""
stock_select = """    ColorSurfaceCacheInfo &info = *ite->second;

    if ((base_format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8 || info.format == SCE_GXM_COLOR_BASE_FORMAT_U8U8U8)
        && base_format != info.format)
        // don't even try to match u8u8u8 with something else
        return std::nullopt;

    if (tiling != info.tiling || info.stride_bytes != stride_bytes) {
        // if the tiling is different, also don't try to match them
        // about the strides, I've yet to see a case where the byte stride is different
        LOG_WARN_ONCE("Surface-as-texture miss (tiling/stride): texture=0x{:X} tiling={}/{} stride={}/{}",
            address, static_cast<int>(tiling), static_cast<int>(info.tiling), stride_bytes, info.stride_bytes);
        return std::nullopt;
    }
"""
v = must_replace(v, custom_select, stock_select, "restore surface selection")

# Builds 476-480 changed this casted texture to SampledImage. Android 4098
# leaves it in ColorAttachmentReadWrite after the transfer.
v = must_replace(
    v,
    "        casted->texture.transition_to(cmd_buffer, vkutil::ImageLayout::SampledImage);",
    "        casted->texture.transition_to(cmd_buffer, vkutil::ImageLayout::ColorAttachmentReadWrite);",
    "restore casted final layout",
)
surface.write_text(v)

# 4) Remove speculative shader behavior changes not present in build 4098.
spirv = src / "vita3k" / "shader" / "src" / "spirv_recompiler.cpp"
p = spirv.read_text()
custom_banks = """    // Create register banks. Vita hardware starts these predictably; leaving
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
stock_banks = """    // Create register banks
    spv_params.ins = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, pa_arr_type, "pa");
    spv_params.uniforms = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, sa_arr_type, "sa");
    spv_params.internals = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, i_arr_type, "internals");
    spv_params.temps = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, temp_arr_type, "r");
    spv_params.predicates = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, pred_arr_type, "p");
    spv_params.indexes = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, index_arr_type, "idx");
    spv_params.outs = b.createVariable(spv::NoPrecision, spv::StorageClassPrivate, o_arr_type, "outs");
"""
p = must_replace(p, custom_banks, stock_banks, "restore private register banks")
spirv.write_text(p)

alu = src / "vita3k" / "shader" / "src" / "translator" / "alu.cpp"
a = alu.read_text()
dual_guess = """        if (result != spv::NoResult && m_b.getNumComponents(result) == 1) {
            result = postprocess_dot_result_for_store(m_b, result, write_mask_dest);
        }

"""
a = must_replace(a, dual_guess, "", "remove DUAL guess")
alu.write_text(a)

uniform = src / "vita3k" / "shader" / "include" / "shader" / "uniform_block.h"
u = uniform.read_text()
custom_uniforms = """struct RenderFragUniformBlock {
    float back_disabled = 0.0f;
    float front_disabled = 0.0f;
    float writing_mask = 0.0f;
    float use_raw_image = 0.0f;
    float res_multiplier = 1.0f;
};
"""
stock_uniforms = """struct RenderFragUniformBlock {
    float back_disabled;
    float front_disabled;
    float writing_mask;
    float use_raw_image;
    float res_multiplier;
};
"""
u = must_replace(u, custom_uniforms, stock_uniforms, "restore fragment uniforms")
uniform.write_text(u)

# Force shader cache invalidation after replacing the 480 translator behavior
# and adding official 4098 fconv_type=0 semantics.
cache = src / "vita3k" / "shader" / "include" / "shader" / "spirv_recompiler.h"
c = cache.read_text()
c = must_replace(c, "static constexpr uint32_t CURRENT_VERSION = 14;",
                 "static constexpr uint32_t CURRENT_VERSION = 15;",
                 "bump shader cache")
cache.write_text(c)

print("VitaJoN 0.48.1 clean Android-4098 parity normalization applied")
PY

# VitaJoN 0.48.2: MoltenVK explicitly documents that PVRTC image contents
# uploaded through a Vulkan staging buffer are malformed. Vita3K's texture
# cache uses exactly a TransferSrc staging buffer for texture uploads, and the
# 481 device log proves Apple/MoltenVK advertises PVRTC so Vita3K selects that
# native path ("Your device support SCE_GXM_TEXTURE_BASE_FORMAT_PVRT").
# Android/Turnip does not have this MoltenVK limitation. Force the already
# existing Vita3K software PVRT decompressor on iOS so uploads become RGBA8.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
texture = src / "vita3k" / "renderer" / "src" / "vulkan" / "texture.cpp"
s = texture.read_text()

old = """    // powerVR only
    const vk::FormatProperties pvrt_support = state.physical_device.getFormatProperties(vk::Format::ePvrtc12BppUnormBlockIMG);
    support_pvrt = static_cast<bool>(pvrt_support.optimalTilingFeatures & vk::FormatFeatureFlagBits::eSampledImage);
"""

new = """    // powerVR only
    const vk::FormatProperties pvrt_support = state.physical_device.getFormatProperties(vk::Format::ePvrtc12BppUnormBlockIMG);
    support_pvrt = static_cast<bool>(pvrt_support.optimalTilingFeatures & vk::FormatFeatureFlagBits::eSampledImage);
#ifdef VITA3K_PLATFORM_IOS
    // MoltenVK limitation: PVRTC content copied from a staging buffer into an
    // optimal-tiled VkImage can be malformed. VKTextureCache uploads textures
    // through a TransferSrc staging buffer, so do not use native PVRTC here.
    // TextureCache::upload_texture will transparently decompress PVRT/PVRTII
    // to RGBA8 using Vita3K's software decoder instead.
    if (support_pvrt) {
        LOG_INFO("iOS/MoltenVK: native PVRTC disabled; using software PVRT -> RGBA8 decompression");
        support_pvrt = false;
    }
#endif
"""

if s.count(old) != 1:
    raise SystemExit(f"PVRTC capability anchor count={s.count(old)}")
s = s.replace(old, new, 1)
texture.write_text(s)

print("VitaJoN 0.48.2 MoltenVK PVRTC staging workaround applied")
PY

# VitaJoN 0.48.3: keep the 482 correctness fix without paying the software
# PVRTC decompression cost. MoltenVK advertises PVRTC1 on Apple GPUs, but its
# Vulkan buffer->image staging path is documented to produce malformed PVRTC
# content. Route PVRTC1 uploads through the underlying Metal texture instead.
# PVRTCII remains on Vita3K's software decoder because Metal exposes PVRTC1.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])

def must_replace(text, old, new, label, count=1):
    n = text.count(old)
    if n != count:
        raise SystemExit(f"{label}: expected {count}, found {n}")
    return text.replace(old, new, count)

cmake = src / "ios" / "CMakeLists.txt"
c = cmake.read_text()
c = must_replace(
    c,
    "    target_include_directories(Vita3KiOS PRIVATE include)\n",
    '    target_include_directories(Vita3KiOS PRIVATE include "${VITA3K_IOS_MOLTENVK_INCLUDE_DIR}")\n',
    "MoltenVK include path",
    1,
)
cmake.write_text(c)

texture = src / "vita3k" / "renderer" / "src" / "vulkan" / "texture.cpp"
t = texture.read_text()
old_482 = """    // powerVR only
    const vk::FormatProperties pvrt_support = state.physical_device.getFormatProperties(vk::Format::ePvrtc12BppUnormBlockIMG);
    support_pvrt = static_cast<bool>(pvrt_support.optimalTilingFeatures & vk::FormatFeatureFlagBits::eSampledImage);
#ifdef VITA3K_PLATFORM_IOS
    // MoltenVK limitation: PVRTC content copied from a staging buffer into an
    // optimal-tiled VkImage can be malformed. VKTextureCache uploads textures
    // through a TransferSrc staging buffer, so do not use native PVRTC here.
    // TextureCache::upload_texture will transparently decompress PVRT/PVRTII
    // to RGBA8 using Vita3K's software decoder instead.
    if (support_pvrt) {
        LOG_INFO("iOS/MoltenVK: native PVRTC disabled; using software PVRT -> RGBA8 decompression");
        support_pvrt = false;
    }
#endif
"""
new_483 = """    // powerVR only
    const vk::FormatProperties pvrt_support = state.physical_device.getFormatProperties(vk::Format::ePvrtc12BppUnormBlockIMG);
    support_pvrt = static_cast<bool>(pvrt_support.optimalTilingFeatures & vk::FormatFeatureFlagBits::eSampledImage);
#ifdef VITA3K_PLATFORM_IOS
    if (support_pvrt)
        LOG_INFO("iOS/MoltenVK: PVRTC1 supported; using direct Metal compressed uploads (Vulkan staging bypassed)");
#endif
"""
t = must_replace(t, old_482, new_483, "replace 482 PVRTC fallback")

ns_anchor = "namespace renderer::vulkan {\n"
bridge_decl = """#ifdef VITA3K_PLATFORM_IOS
extern "C" bool vita3k_ios_upload_pvrtc_metal(
    VkImage image, VkQueue queue, uint32_t mip_level, uint32_t array_slice,
    uint32_t width, uint32_t height, const void *bytes);
#endif

"""
if bridge_decl not in t:
    t = must_replace(t, ns_anchor, ns_anchor + "\n" + bridge_decl, "PVRTC bridge declaration")

fmt_anchor = """    vk::Format vk_format = texture::translate_format(base_format);
    if (gxm::is_bcn_format(base_format) && !support_dxt)
        // texture will be decompressed
        vk_format = bcn_to_rgba8(vk_format);
    if (gxm_texture.gamma_mode)
        vk_format = linear_to_srgb(vk_format);
"""
fmt_new = """    vk::Format vk_format = texture::translate_format(base_format);
#ifdef VITA3K_PLATFORM_IOS
    const bool direct_pvrtc1 = support_pvrt
        && (base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT2BPP
            || base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT4BPP);
    if (direct_pvrtc1) {
        if (base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT2BPP)
            vk_format = gxm_texture.gamma_mode
                ? vk::Format::ePvrtc12BppSrgbBlockIMG
                : vk::Format::ePvrtc12BppUnormBlockIMG;
        else
            vk_format = gxm_texture.gamma_mode
                ? vk::Format::ePvrtc14BppSrgbBlockIMG
                : vk::Format::ePvrtc14BppUnormBlockIMG;
    } else
#endif
    {
        if (gxm::is_bcn_format(base_format) && !support_dxt)
            // texture will be decompressed
            vk_format = bcn_to_rgba8(vk_format);
        if (gxm_texture.gamma_mode)
            vk_format = linear_to_srgb(vk_format);
    }
"""
t = must_replace(t, fmt_anchor, fmt_new, "PVRTC image format")

upload_anchor = """void VKTextureCache::upload_texture_impl(SceGxmTextureBaseFormat base_format, uint32_t width, uint32_t height,
    uint32_t mip_index, const void *pixels, int face, uint32_t pixels_per_stride) {
    if (!is_texture_transfer_ready)
        prepare_staging_buffer();

    vkutil::Image &image = current_texture->texture;
    TextureStagingBuffer &staging_buffer = staging_buffers[staging_idx];

    if (face > 0)
        face--;
"""
upload_new = """void VKTextureCache::upload_texture_impl(SceGxmTextureBaseFormat base_format, uint32_t width, uint32_t height,
    uint32_t mip_index, const void *pixels, int face, uint32_t pixels_per_stride) {
#ifdef VITA3K_PLATFORM_IOS
    const bool direct_pvrtc1 = support_pvrt
        && (base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT2BPP
            || base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT4BPP);
    if (direct_pvrtc1) {
        const uint32_t slice = face > 0 ? static_cast<uint32_t>(face - 1) : 0u;
        const bool ok = vita3k_ios_upload_pvrtc_metal(
            static_cast<VkImage>(current_texture->texture.image),
            static_cast<VkQueue>(state.general_queue),
            mip_index, slice, width, height, pixels);
        if (!ok) {
            LOG_ERROR("iOS direct Metal PVRTC upload failed: {}x{} mip={} slice={}",
                width, height, mip_index, slice);
        } else {
            LOG_INFO_ONCE("VitaJoN 0.48.3 direct Metal PVRTC1 upload active");
        }
        ios_direct_pvrtc_active = true;
        return;
    }
#endif

    if (!is_texture_transfer_ready)
        prepare_staging_buffer();

    vkutil::Image &image = current_texture->texture;
    TextureStagingBuffer &staging_buffer = staging_buffers[staging_idx];

    if (face > 0)
        face--;
"""
t = must_replace(t, upload_anchor, upload_new, "direct PVRTC upload")

done_anchor = """void VKTextureCache::upload_done() {
    // transition the texture back to read only
"""
done_new = """void VKTextureCache::upload_done() {
#ifdef VITA3K_PLATFORM_IOS
    if (ios_direct_pvrtc_active) {
        current_texture->texture.layout = vkutil::ImageLayout::SampledImage;
        ios_direct_pvrtc_active = false;
        cmd_buffer = nullptr;
        is_texture_transfer_ready = false;
        return;
    }
#endif
    // transition the texture back to read only
"""
t = must_replace(t, done_anchor, done_new, "direct PVRTC upload_done")
texture.write_text(t)

types = src / "vita3k" / "renderer" / "include" / "renderer" / "vulkan" / "types.h"
h = types.read_text()
member_anchor = """    bool is_texture_transfer_ready = false;

    VKTextureCache(VKState &state);
"""
member_new = """    bool is_texture_transfer_ready = false;
#ifdef VITA3K_PLATFORM_IOS
    bool ios_direct_pvrtc_active = false;
#endif

    VKTextureCache(VKState &state);
"""
h = must_replace(h, member_anchor, member_new, "PVRTC active member")
types.write_text(h)

cache = src / "vita3k" / "renderer" / "src" / "texture" / "cache.cpp"
k = cache.read_text()
pvrt_case = """        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRT2BPP:
        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRT4BPP:
        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRTII2BPP:
        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRTII4BPP:
            if (support_pvrt) {
                LOG_INFO_ONCE("Your device support SCE_GXM_TEXTURE_BASE_FORMAT_PVRT");
                break;
            }
            if (!is_swizzled)
                LOG_ERROR_ONCE("Unhandled non-swizzled PVRT format, please report it to the developers");

            texture_data_decompressed.resize(pixels_per_stride * memory_height * 4);
            // this actually also unswizzles the texture
            decompress_compressed_texture(base_format, texture_data_decompressed.data(), pixels, pixels_per_stride, memory_height);
            bytes_per_pixel = 4;
            bpp = 32;
            upload_format = SCE_GXM_TEXTURE_BASE_FORMAT_U8U8U8U8;
            pixels = texture_data_decompressed.data();
            break;
"""
pvrt_case_new = """        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRT2BPP:
        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRT4BPP:
        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRTII2BPP:
        case SCE_GXM_TEXTURE_BASE_FORMAT_PVRTII4BPP:
#ifdef VITA3K_PLATFORM_IOS
            if (support_pvrt
                && (base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT2BPP
                    || base_format == SCE_GXM_TEXTURE_BASE_FORMAT_PVRT4BPP)) {
                LOG_INFO_ONCE("iOS: PVRTC1 stays compressed for direct Metal upload");
                break;
            }
#else
            if (support_pvrt) {
                LOG_INFO_ONCE("Your device support SCE_GXM_TEXTURE_BASE_FORMAT_PVRT");
                break;
            }
#endif
            if (!is_swizzled)
                LOG_ERROR_ONCE("Unhandled non-swizzled PVRT format, please report it to the developers");

            texture_data_decompressed.resize(pixels_per_stride * memory_height * 4);
            // this actually also unswizzles the texture
            decompress_compressed_texture(base_format, texture_data_decompressed.data(), pixels, pixels_per_stride, memory_height);
            bytes_per_pixel = 4;
            bpp = 32;
            upload_format = SCE_GXM_TEXTURE_BASE_FORMAT_U8U8U8U8;
            pixels = texture_data_decompressed.data();
            break;
"""
k = must_replace(k, pvrt_case, pvrt_case_new, "PVRT generic decode split")
cache.write_text(k)

frontend = src / "ios" / "src" / "NativeFrontend.mm"
n = frontend.read_text()
include_anchor = """#import <AVFoundation/AVFoundation.h>
#import <GameController/GameController.h>
#import <QuartzCore/QuartzCore.h>
"""
include_new = """#import <AVFoundation/AVFoundation.h>
#import <GameController/GameController.h>
#import <Metal/Metal.h>
#import <QuartzCore/QuartzCore.h>
#include <MoltenVK/vk_mvk_moltenvk.h>
"""
n = must_replace(n, include_anchor, include_new, "Metal/MoltenVK includes")

bridge_impl = r'''

extern "C" bool vita3k_ios_upload_pvrtc_metal(
    VkImage image, VkQueue queue, uint32_t mip_level, uint32_t array_slice,
    uint32_t width, uint32_t height, const void *bytes) {
    @autoreleasepool {
        if (!image || !queue || !bytes || width == 0 || height == 0)
            return false;

        id<MTLTexture> destination = nil;
        vkGetMTLTextureMVK(image, &destination);
        if (!destination)
            return false;

        const MTLRegion region = MTLRegionMake2D(0, 0, width, height);

        if (destination.storageMode != MTLStorageModePrivate) {
            [destination replaceRegion:region
                           mipmapLevel:mip_level
                                 slice:array_slice
                             withBytes:bytes
                           bytesPerRow:0
                         bytesPerImage:0];
            return true;
        }

        id<MTLDevice> device = destination.device;
        if (!device)
            return false;

        MTLTextureDescriptor *desc =
            [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:destination.pixelFormat
                                                               width:width
                                                              height:height
                                                           mipmapped:NO];
        desc.storageMode = MTLStorageModeShared;
        desc.usage = MTLTextureUsageShaderRead;

        id<MTLTexture> staging = [device newTextureWithDescriptor:desc];
        if (!staging)
            return false;

        [staging replaceRegion:region
                   mipmapLevel:0
                         slice:0
                     withBytes:bytes
                   bytesPerRow:0
                 bytesPerImage:0];

        id<MTLCommandQueue> mtl_queue = nil;
        vkGetMTLCommandQueueMVK(queue, &mtl_queue);
        if (!mtl_queue)
            return false;

        id<MTLCommandBuffer> command_buffer = [mtl_queue commandBuffer];
        if (!command_buffer)
            return false;
        id<MTLBlitCommandEncoder> blit = [command_buffer blitCommandEncoder];
        if (!blit)
            return false;

        [blit copyFromTexture:staging
                 sourceSlice:0
                 sourceLevel:0
                sourceOrigin:MTLOriginMake(0, 0, 0)
                  sourceSize:MTLSizeMake(width, height, 1)
                   toTexture:destination
            destinationSlice:array_slice
            destinationLevel:mip_level
           destinationOrigin:MTLOriginMake(0, 0, 0)];
        [blit endEncoding];

        [command_buffer addCompletedHandler:^(__unused id<MTLCommandBuffer> cb) {
            (void)staging;
        }];
        [command_buffer commit];
        return true;
    }
}
'''
if "vita3k_ios_upload_pvrtc_metal(" in n:
    raise SystemExit("PVRTC bridge implementation already present")
n += bridge_impl
frontend.write_text(n)

print("VitaJoN 0.48.3 native Metal PVRTC1 fast path applied")
PY

# VitaJoN 0.48.3: make an unexpected return to the library diagnosable.
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / "ios" / "src" / "UpstreamMain.cpp"
s = p.read_text()

repls = [
("""            case SDL_EVENT_TERMINATING:
                app_terminating = true;
                running = false;
                break;
""",
"""            case SDL_EVENT_TERMINATING:
                LOG_WARN("iOS session exit trigger: SDL_EVENT_TERMINATING");
                app_terminating = true;
                running = false;
                break;
"""),
("""            case SDL_EVENT_QUIT:
            case SDL_EVENT_WINDOW_CLOSE_REQUESTED:
                // In-game menu "Quit Game" pushes SDL_EVENT_QUIT: end the
                // session and fall back to the library.
                running = false;
                break;
""",
"""            case SDL_EVENT_QUIT:
            case SDL_EVENT_WINDOW_CLOSE_REQUESTED:
                // In-game menu "Quit Game" pushes SDL_EVENT_QUIT: end the
                // session and fall back to the library.
                LOG_WARN("iOS session exit trigger: SDL event {}", static_cast<unsigned>(event.type));
                running = false;
                break;
"""),
("""        if (auto request = emuenv->take_app_launch_request()) {
            // In-process relaunch (LoadExec) is not supported yet on iOS.
            LOG_WARN("Title requested relaunch of '{}'; stopping instead.", request->self_path);
            running = false;
        }

        if (!session_controller.is_running())
            running = false;
""",
"""        if (auto request = emuenv->take_app_launch_request()) {
            // In-process relaunch (LoadExec) is not supported yet on iOS.
            LOG_WARN("Title requested relaunch of '{}'; stopping instead.", request->self_path);
            LOG_WARN("iOS session exit trigger: guest LoadExec request");
            running = false;
        }

        if (!session_controller.is_running()) {
            LOG_WARN("iOS session exit trigger: AppSessionController no longer running");
            running = false;
        }
""")
]
for old,new in repls:
    if s.count(old) != 1:
        raise SystemExit("session-exit diagnostic anchor mismatch")
    s = s.replace(old,new,1)
p.write_text(s)
print("VitaJoN 0.48.3 session exit diagnostics applied")
PY

