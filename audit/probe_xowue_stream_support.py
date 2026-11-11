#!/usr/bin/env python3
"""Extract supporting generated AOT functions for the Wolverine stream poll loop."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

FUNC = re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{')
COMMENT = re.compile(r'(?m)^\s*//\s+(.+?)\s*$')
OWNERS = (
    0x82495BF8,  # caller which asks for the stream bytes
    0x82575250,  # stream range / chunk update callback
    0x82575480,  # polling wrapper with vtable completion loop
    0x82575108,  # chunk request helper
    0x82574348,  # virtual stream-provider read submission callback (observed in Build 138)
    0x82573CB0,  # implementation behind the observed 0x82574348 wrapper
    0x824A7DF0,  # async stream service interface getter used by the observed callsite
    0x8257D290,  # stream provider's request enqueue/dispatch implementation
    0x822A0608,  # request descriptor preparation immediately before enqueue
    0x82574508,  # per-request queue slot submission called by the stream enqueue routine
    0x82573620,  # async stream-manager setup/use path
    0x82573AE8,  # async stream-manager setup/use path
    0x822A0160,  # stream metadata helper
    0x822A00C0,  # stream metadata helper
    0x82C3C4D8,  # timebase helper
    0x82C3EE78,  # wait/yield helper
    0x82C2A290,  # buffer copy / advance helper
    0x82573B80,  # initialization/worker routine entered by sub_82573AE8
    0x82C4BE30,  # wait helper reached from Bink video worker threads
    0x82690DC0,  # XOWUE_BINK_VIDEO_THREAD_START entry
    0x83268358,  # XOWUE_BINK_DECODER_THREAD_START entry
    0x82573090,  # worker queue item processor called by sub_82573B80
    0x832681D8,  # Bink decoder worker transition handler
    0x82C410D0,  # Bink decoder worker completion/reset helper
    0x82690DC8,  # actual video thread body behind the entry thunk
    0x82573398,  # per-item stream worker dispatcher called by sub_82573090
    0x82573000,  # worker item ready/poll helper
    0x82494A60,  # item cache/request transition helper
    0x82499150,  # per-priority queue callback builder
    0x825734B8,  # worker's second queue poll helper
    0x824AD010,  # worker's final queue poll/dispatch helper
    0x831EDA60,  # global async stream manager initializer
    0x82494EB8,  # async scheduler task stage 1
    0x82495770,  # async scheduler task stage 2
    0x82495DC8,  # async scheduler task stage 4
    0x82496160,  # async scheduler task stage 5
    0x824969E0,  # async scheduler task stage 6
    0x82495F50,  # async scheduler task stage 7
    0x82496338,  # async scheduler task stage 8
    0x824970B0,  # async scheduler task stage 9
    0x824972B0,  # async scheduler task stage 10
    0x82494E20,  # async scheduler post-stage check
    0x82497450,  # async scheduler finalize helper
    0x82494978,  # async event/work object factory
    0x824989F0,  # stream task descriptor builder
    0x824B3F18,  # synchronization object allocator
    0x8243C750,  # synchronization object release
    0x824B4CD8,  # scheduler notification helper
    0x82C40F70,  # decoder work batch selector
    0x82C45080,  # mutant release exception path
    0x82C3FC70,  # video thread completion helper
    0x82B45838,  # hot function called repeatedly by video worker T11 in Build 142.1
    0x82B3C6D8,  # adjacent worker helper observed in the same T11 trace
    0x82C3C5D0,  # immediate timebase helper called by the T11 hot loop
    0x83269920,  # additional hot worker helper sampled on T11
    0x82C25840,  # additional host/guest scheduler helper sampled on T11
    0x82B53FA8,  # timing/pacing wait routine called by the hot T11 function
    0x82573DE0,  # worker/request routine containing the final T9 helper call
    0x82C2A1F0,  # guest memory fill/clear helper called by worker T9
)

# Resolve a runtime PC to the actual generated AOT function containing it.
PC_TARGETS = (0x824E72B4, 0x82573E64)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ppc-dir",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    wanted=set(OWNERS)
    found={}
    found_pcs={}
    for file in sorted(args.ppc_dir.glob("ppc_recomp.*.cpp")):
        src=file.read_text("utf-8")
        entries=list(FUNC.finditer(src))
        for i,entry in enumerate(entries):
            owner=int(entry.group(1)[4:],16)
            end=entries[i+1].start() if i+1<len(entries) else len(src)
            body=src[entry.end():end]
            comment_count=len(COMMENT.findall(body))
            for pc in PC_TARGETS:
                if owner <= pc < owner + comment_count * 4:
                    found_pcs[pc]={"requested_pc":f"0x{pc:08X}","owner":f"0x{owner:08X}",
                                   "name":f"sub_{owner:08X}","file":file.name,
                                   "instruction_index":(pc-owner)//4,"body":body}
            if owner in wanted:
                found[owner]={"name":f"sub_{owner:08X}","file":file.name,
                              "instruction_comment_count":comment_count,
                              "body":body}
    missing=[f"0x{x:08X}" for x in OWNERS if x not in found]
    result={"purpose":"Verbatim generated AOT bodies for stream polling and read completion investigation.",
            "functions":[found[x] for x in OWNERS if x in found],
            "containing_functions":[found_pcs[x] for x in PC_TARGETS if x in found_pcs],
            "missing_pc_targets":[f"0x{x:08X}" for x in PC_TARGETS if x not in found_pcs],
            "missing":missing,
            "important_runtime_call_sites":{
                "outer_vtable_call":"0x82495C60",
                "inner_vtable_call":"0x8257550C",
                "inner_return_test":"0x82575510",
                "inner_retry_branch":"0x82575514",
                "yield_call":"0x825754F0",
                "stream_dispatch_calls":["0x825753D0","0x82575474"],
                "observed_submission_callback":"0x82574348",
                "observed_submission_implementation":"0x82573CB0",
                "observed_service_getter":"0x824A7DF0",
                "observed_request_enqueue":"0x8257D290",
                "observed_request_prepare":"0x822A0608",
                "observed_queue_slot_submit":"0x82574508",
                "observed_submission_site":"0x82575244",
                "expected_completion_site":"0x82575474",
                "video_thread_entry":"0x82690DC0",
                "decoder_thread_entry":"0x83268358",
                "video_thread_wait_helper":"0x82C4BE30",
                "stream_worker_init":"0x82573B80",
                "video_thread_wait_return_lr":"0x824E72B4",
                "stream_worker_queue_item":"0x82573090",
                "decoder_worker_transition":"0x832681D8",
                "decoder_worker_completion":"0x82C410D0",
                "video_thread_body":"0x82690DC8",
                "stream_worker_item_dispatch":"0x82573398",
                "stream_worker_item_poll":"0x82573000",
                "stream_cache_request_transition":"0x82494A60",
                "stream_priority_queue_builder":"0x82499150",
                "stream_worker_secondary_poll":"0x825734B8",
                "stream_worker_final_poll":"0x824AD010",
                "async_stream_manager_initializer":"0x831EDA60",
                "scheduler_task_stages":["0x82494EB8","0x82495770","0x82495BF8","0x82495DC8","0x82496160","0x824969E0","0x82495F50","0x82496338","0x824970B0","0x824972B0"],
                "scheduler_post_stage":["0x82494E20","0x82497450"],
                "decoder_work_batch":"0x82C40F70",
                "video_thread_completion":"0x82C3FC70"
            }}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("XOWUE_STREAM_SUPPORT_AOT_SOURCE "+json.dumps({
        "found":[{"name":f["name"],"file":f["file"],
                  "instruction_comments":f["instruction_comment_count"],
                  "body_chars":len(f["body"])} for f in result["functions"]],
        "containing_functions":[{"pc":f["requested_pc"],"owner":f["owner"],"file":f["file"],
                                 "instruction_index":f["instruction_index"]}
                                for f in result["containing_functions"]],
        "missing":missing,"missing_pc_targets":result["missing_pc_targets"]}))
    required=(0x82575480,0x82575108,0x82574348,0x82573CB0,0x824A7DF0,0x8257D290,0x822A0608,0x82574508,0x82573B80,0x82C4BE30,0x82690DC0,0x83268358,0x82573090,0x832681D8,0x82C410D0,0x82690DC8,0x82573398,0x82573000,0x82494A60,0x82499150,0x825734B8,0x824AD010,0x831EDA60,0x82494EB8,0x82495770,0x82495DC8,0x82496160,0x824969E0,0x82495F50,0x82496338,0x824970B0,0x824972B0,0x82494E20,0x82497450,0x82494978,0x824989F0,0x824B3F18,0x8243C750,0x824B4CD8,0x82C40F70,0x82C45080,0x82C3FC70,0x82B45838,0x82B3C6D8,0x82C3C5D0,0x83269920,0x82C25840,0x82B53FA8,0x82573DE0,0x82C2A1F0)
    missing_required=[f"0x{x:08X}" for x in required if x not in found]
    if missing_required:
        raise SystemExit("Required stream poll / callback source missing: "+", ".join(missing_required))
    if result["missing_pc_targets"]:
        raise SystemExit("Required runtime PC not mapped to an AOT function: "+", ".join(result["missing_pc_targets"]))

if __name__=="__main__": main()
