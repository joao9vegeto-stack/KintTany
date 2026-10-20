#!/usr/bin/env python3
"""M7.71 post-stage refinement: physical frontier forensic telemetry and concise reports.
Runs after M7.70 unpacks and registers ALL 3835 handlers; no game-code modifications.
"""
import sys
from pathlib import Path

def one(s, old, new, label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{label}: anchor count {n}, expected 1: {old[:70]!r}')
    return s.replace(old,new,1)

def main(root):
    changes={}
    name='runtime/ppu_bridge.h'
    s=(root/name).read_text()
    s=one(s, '} ar_aot_trace;\nvoid ar_trace_snapshot(ar_aot_trace *out);',
'''    /* M7.71: exact native frontier entry and handler returns, NOT first visits. */
    uint32_t m771_enters,m771_returns,m771_child_calls;
    int32_t m771_status,m771_fault,m771_child_status;
    uint64_t m771_r2_entry,m771_r2_exit,m771_lr_entry,m771_sp_entry;
    uint64_t m771_r3_entry,m771_cia_exit,m771_child_r2;
} ar_aot_trace;
void ar_trace_snapshot(ar_aot_trace *out);''',name)
    changes[name]=s
    name='runtime/ppu_bridge.c';s=(root/name).read_text()
    s=one(s,'static uint32_t aot_hash(uint32_t pc){',
'''/* Physical-entry observation only. Never patch game registers or memory. */
static uint32_t m771_enters,m771_returns,m771_child_calls,m771_inside;
static int32_t m771_status,m771_fault,m771_child_status;
static uint64_t m771_r2_entry,m771_r2_exit,m771_lr_entry,m771_sp_entry;
static uint64_t m771_r3_entry,m771_cia_exit,m771_child_r2;
static uint32_t aot_hash(uint32_t pc){''',name)
    s=one(s,' out->m768_last_hle_depth=m768_last_hle_depth;',
''' out->m768_last_hle_depth=m768_last_hle_depth;
 out->m771_enters=m771_enters;out->m771_returns=m771_returns;
 out->m771_child_calls=m771_child_calls;
 out->m771_status=m771_status;out->m771_fault=m771_fault;
 out->m771_child_status=m771_child_status;
 out->m771_r2_entry=m771_r2_entry;out->m771_r2_exit=m771_r2_exit;
 out->m771_lr_entry=m771_lr_entry;out->m771_sp_entry=m771_sp_entry;
 out->m771_r3_entry=m771_r3_entry;out->m771_cia_exit=m771_cia_exit;
 out->m771_child_r2=m771_child_r2;''',name)
    s=one(s,'    int status=fn(c);',
'''    const int is_frontier=(pc==UINT32_C(0x0052a740));
    const int is_nested=(m771_inside && pc==UINT32_C(0x0052e3f4));
    if(is_frontier){
      m771_inside++;m771_enters++;
      m771_r2_entry=c->gpr[2];m771_lr_entry=c->lr;
      m771_sp_entry=c->gpr[1];m771_r3_entry=c->gpr[3];
    }
    if(is_nested){m771_child_calls++;m771_child_r2=c->gpr[2];}
    int status=fn(c);
    if(is_nested)m771_child_status=status;
    if(is_frontier){
      m771_returns++;m771_status=status;m771_fault=fault;
      m771_r2_exit=c->gpr[2];m771_cia_exit=c->cia;
      m771_inside--;
    }''',name)
    s=one(s,'  m767_fail_pc=m767_fail_reason=m767_failed_handler_pc=0;',
'''  m767_fail_pc=m767_fail_reason=m767_failed_handler_pc=0;
  m771_enters=m771_returns=m771_child_calls=m771_inside=0;
  m771_status=m771_fault=m771_child_status=0;
  m771_r2_entry=m771_r2_exit=m771_lr_entry=m771_sp_entry=0;
  m771_r3_entry=m771_cia_exit=m771_child_r2=0;''',name)
    changes[name]=s
    name='ios/ARProbeApp.m';s=(root/name).read_text()
    # The concise export is the default; retain the existing full forensic report
    # as a separate on-demand technical TXT for other agents.
    begin=s.index('- (NSString *)arUnifiedPpuText {')
    end=s.index('- (void)arCopyAllPpuText {',begin)
    slim='''- (NSString *)arUnifiedPpuText {
  NSDictionary *e=self.m750Run;
  NSString *(^v)(NSString *)=^NSString*(NSString *key){
    return e[key]?[e[key] description]:@"NÃO MEDIDO";
  };
  NSString *(^h)(NSString *)=^NSString*(NSString *key){
    return e[key]?[NSString stringWithFormat:@"0x%08X",[e[key] unsignedIntValue]]:@"NÃO MEDIDO";
  };
  NSString *(^h64)(NSString *)=^NSString*(NSString *key){
    return e[key]?[NSString stringWithFormat:@"0x%016llX",[e[key] unsignedLongLongValue]]:@"NÃO MEDIDO";
  };
  return [NSString stringWithFormat:
    @"ASCENSIONRECOMP — EXECUÇÃO ATUAL / AOT-v13\\n"
     "Branch=%s | SHA=%s | Actions=%s | RunID=%s\\n"
     "App=%@ | NPUA80918 | teste físico=%@ | momento=%@\\n\\n"
     "RESULTADO REAL\\n"
     "Registradas=%@ | AOT distintas=%@ | despachos ARM64=%@ | PPC interpretadas=%@\\n"
     "Resultado guest=%@ | parada=%@ | opcode=%@ | último AOT=%@\\n"
     "Guest FS: cellFsOpen=%@ | cellFsRead=%@ | bytes lidos=%@\\n"
     "PSARC, RSX e quadro do jogo=SEM EVIDENCIA\\n\\n"
     "M7.70: REGISTROS DO LOTE (sem inflar execução)\\n"
     "Examinados=%@ | novos=%@ | conflitos=%@ | rejeitados=%@\\n"
     "Frontier 0x0052A740: handler vinculado=%@ | primeiro despacho observado=%@\\n\\n"
     "M7.71 FORENSE NATIVA — entrada NÃO é conclusão\\n"
     "Entradas=%@ | retornos=%@ | status handler=%@ | fault VM=%@\\n"
     "TOC r2 entrada=%@ | r2 saída=%@ | LR entrada=%@ | SP entrada=%@\\n"
     "r3 entrada=%@ | CIA após retorno=%@\\n"
     "Chamada aninhada 0x0052E3F4: entradas=%@ | status=%@ | TOC=%@\\n"
     "Parada guest: motivo=%@ | PC=%@ | opcode RAM=%@\\n\\n"
     "MARCO (M7.69 física: 9619 AOT, 154 distintas, 1912 despachos)\\n"
     "Agora: 13252 AOT, 155 distintas, 1914 despachos na M7.70 física\\n"
     "Não representa novo resultado sem teste desta build.\\n"
     "USRDIR HOST=%@ — NÃO é cellFsRead.\\n"
     "Diagnóstico técnico legado integral disponível em TXT separado.\\n",
    AR_M750_BUILD_BRANCH,AR_M750_BUILD_SHA,
    AR_M750_BUILD_RUN_NUMBER,AR_M750_BUILD_RUN_ID,
    ARCurrentRelease(),e?@"SIM":@"NÃO MEDIDO",v(@"when"),
    v(@"aot"),v(@"unique"),v(@"dispatches"),v(@"fallback"),
    v(@"rc"),h(@"stop"),h(@"opcode"),h(@"last_aot"),
    v(@"fs_open_calls"),v(@"fs_read_calls"),v(@"fs_bytes"),
    v(@"m771_examined"),v(@"m771_new"),v(@"m771_conflicts"),v(@"m771_rejected"),
    v(@"m771_frontier_present"),v(@"m771_enters"),
    v(@"m771_enters"),v(@"m771_returns"),v(@"m771_status"),v(@"m771_fault"),
    h64(@"m771_r2_entry"),h64(@"m771_r2_exit"),h64(@"m771_lr_entry"),h64(@"m771_sp_entry"),
    h64(@"m771_r3_entry"),h64(@"m771_cia_exit"),
    v(@"m771_child_calls"),v(@"m771_child_status"),h64(@"m771_child_r2"),
    v(@"m767_stop_reason"),h(@"m767_fail_pc"),h(@"opcode"),
    self.m750HostObservation?:@"NÃO MEDIDO"];
}
'''
    legacy=s[begin:end].replace('- (NSString *)arUnifiedPpuText {',
                                '- (NSString *)arLegacyFullPpuText {',1)
    s=s[:begin]+slim+legacy+s[end:]
    s=one(s,'          @"m767_stop_reason":@(measured.m767_fail_reason),',
'''          @"m767_stop_reason":@(measured.m767_fail_reason),
          @"m771_enters":@(measured.m771_enters),
          @"m771_returns":@(measured.m771_returns),
          @"m771_status":@(measured.m771_status),
          @"m771_fault":@(measured.m771_fault),
          @"m771_r2_entry":@(measured.m771_r2_entry),
          @"m771_r2_exit":@(measured.m771_r2_exit),
          @"m771_lr_entry":@(measured.m771_lr_entry),
          @"m771_sp_entry":@(measured.m771_sp_entry),
          @"m771_r3_entry":@(measured.m771_r3_entry),
          @"m771_cia_exit":@(measured.m771_cia_exit),
          @"m771_child_calls":@(measured.m771_child_calls),
          @"m771_child_status":@(measured.m771_child_status),
          @"m771_child_r2":@(measured.m771_child_r2),''',name)
    marker='    NSMutableArray *firstVisits=[NSMutableArray arrayWithCapacity:measured.first_count];'
    s=one(s,marker,'''    if(self.m750Run){
      NSMutableDictionary *a=[self.m750Run mutableCopy];
      a[@"m771_examined"]=@(m770Stats[0]);
      a[@"m771_new"]=@(m770Stats[1]);
      a[@"m771_conflicts"]=@(m770Stats[3]);
      a[@"m771_rejected"]=@(m770Stats[4]);
      a[@"m771_frontier_present"]=@(m770Stats[6]);
      self.m750Run=[a copy];
    }
    [graphReport appendFormat:
      @"M7.71 FORENSE 0x0052A740 entradas=%u retornos=%u status=%d fault=%d"
       " TOC_entrada=0x%llX TOC_saida=0x%llX LR=0x%llX SP=0x%llX"
       " r3=0x%llX CIA_saida=0x%llX nested_52E3F4=%u nested_rc=%d nested_TOC=0x%llX\\n",
       measured.m771_enters,measured.m771_returns,
       measured.m771_status,measured.m771_fault,
       (unsigned long long)measured.m771_r2_entry,
       (unsigned long long)measured.m771_r2_exit,
       (unsigned long long)measured.m771_lr_entry,
       (unsigned long long)measured.m771_sp_entry,
       (unsigned long long)measured.m771_r3_entry,
       (unsigned long long)measured.m771_cia_exit,
       measured.m771_child_calls,measured.m771_child_status,
       (unsigned long long)measured.m771_child_r2];
'''+marker,name)
    s=one(s,'      @"m770_examined_runtime":@(m770Stats[0]),',
'''      @"m771_frontier_enters":@(measured.m771_enters),
      @"m771_frontier_returns":@(measured.m771_returns),
      @"m771_handler_status":@(measured.m771_status),
      @"m771_fault":@(measured.m771_fault),
      @"m771_r2_entry":[NSString stringWithFormat:@"0x%llX",(unsigned long long)measured.m771_r2_entry],
      @"m771_child_calls":@(measured.m771_child_calls),
      @"m771_child_status":@(measured.m771_child_status),
      @"m770_examined_runtime":@(m770Stats[0]),''',name)
    s=one(s,'    self.ppuSummary=[NSString stringWithFormat:',
          '    if(measured.m771_enters && native[7]==0x0052A740u)\n'
          '      pendingText=[NSString stringWithFormat:\n'
          '        @"AOT 0x0052A740: ENTRADA COMPROVADA, handler rc=%d,"\n'
          '         " nested_52E3F4=%u, parada=0x%08X (causa a investigar).",\n'
          '         measured.m771_status,measured.m771_child_calls,native[7]];\n'
          '    self.ppuSummary=[NSString stringWithFormat:',name)
    s=one(s,'    if((int)continuous[0]!=-1314 || continuous[3]!=0x4e800421u)',
'''    self.ppuSummary=[self.ppuSummary stringByAppendingFormat:
      @"\\nFrontier 0x0052A740: entrada=%u retorno=%u status=%d nested=%u r2=0x%llX",
      measured.m771_enters,measured.m771_returns,measured.m771_status,
      measured.m771_child_calls,(unsigned long long)measured.m771_r2_entry];
    if((int)continuous[0]!=-1314 || continuous[3]!=0x4e800421u)''',name)
    s=one(s,'- (void)arExportPpuText {',
'''- (void)arExportDetailedPpuText {
    if(!self.ppuReport.length)return;
    NSDateFormatter *d=[NSDateFormatter new];
    d.locale=[NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    d.dateFormat=@"yyyyMMdd-HHmmss";
    NSString *name=[NSString stringWithFormat:@"AscensionRecomp-%@-TECNICO-NPUA80918-%@.txt",
      ARCurrentRelease(),[d stringFromDate:[NSDate date]]];
    NSURL *docs=[[[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory
        inDomains:NSUserDomainMask] firstObject];
    NSURL *url=[docs URLByAppendingPathComponent:name isDirectory:NO];
    if(![[self arLegacyFullPpuText] writeToURL:url atomically:YES
              encoding:NSUTF8StringEncoding error:NULL])return;
    UIActivityViewController *share=[[UIActivityViewController alloc]
       initWithActivityItems:@[url] applicationActivities:nil];
    UIViewController *presenter=self.window.rootViewController.presentedViewController
                                ?: self.window.rootViewController;
    UIPopoverPresentationController *pop=share.popoverPresentationController;
    if(pop){pop.sourceView=presenter.view;pop.sourceRect=presenter.view.bounds;}
    [presenter presentViewController:share animated:YES completion:nil];
}
- (void)arExportPpuText {''',name)
    s=one(s,'          message:@"Status, lote PPC, AOT_EXEC, grafo e diagnósticos em um só lugar."',
          '          message:@"Resumo curto por padrão; relatório técnico legado separado."',name)
    s=one(s,'[menu addAction:[UIAlertAction actionWithTitle:@"Salvar TXT · Arquivos"',
'''[menu addAction:[UIAlertAction actionWithTitle:@"Compartilhar TXT técnico completo"
          style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a){
          [self arExportDetailedPpuText];
    }]];
    [menu addAction:[UIAlertAction actionWithTitle:@"Salvar TXT · Arquivos"''',name)
    s=one(s,'[diagnostics setTitle:@"Relatório completo · visualizar / TXT" forState:UIControlStateNormal];',
           '[diagnostics setTitle:@"Relatórios · resumo / técnico" forState:UIControlStateNormal];',name)
    # Keep the established discoverability string for UI/VoiceOver regression
    # while the visible button has the more accurate concise/technical label.
    s=one(s,'diagnostics.accessibilityLabel=@"Relatório completo: status AOT, PPC, grafo, HLE e exportar TXT";',
       'diagnostics.accessibilityLabel=@"Relatório completo · visualizar / TXT: resumo atual ou diagnóstico técnico avançado";',name)
    changes[name]=s
    for path,contents in changes.items(): (root/path).write_text(contents)
    print('M7.71 staged: exact entry and exit forensic; compact AOT-v13; separate full technical export. Files:',list(changes))

if __name__=='__main__':main(Path(sys.argv[1]).resolve())