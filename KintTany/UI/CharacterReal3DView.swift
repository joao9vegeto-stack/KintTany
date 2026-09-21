import SwiftUI
import WebKit
import UIKit

struct CharacterReal3DView: UIViewRepresentable {
    let cookie: String
    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKNavigationDelegate {
        weak var webView: WKWebView?
        private var lastX: CGFloat = 0

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            isolate(webView)
        }

        func isolate(_ webView: WKWebView) {
            let js = """
            (() => {
              if (window.__portraitReady) return;
              window.__portraitReady = true;
              const pick = () => {
                const a=[...document.querySelectorAll('canvas')];
                const c=a.find(x=>x.width===680&&x.height===470) || a.filter(x=>x.width>=500&&x.height>=350).sort((x,y)=>y.width*y.height-x.width*x.height)[0];
                if(!c) return false;
                window.__portraitCanvas=c;
                document.documentElement.style.cssText+='background:transparent!important;overflow:hidden!important';
                document.body.style.cssText+='margin:0!important;background:transparent!important;overflow:hidden!important';
                [...document.body.children].forEach(e=>{if(e===c||e.contains(c))return;e.style.visibility='hidden';e.style.pointerEvents='none';});
                let p=c.parentElement; while(p&&p!==document.body){p.style.visibility='visible';p.style.background='transparent';p.style.overflow='visible';p=p.parentElement;}
                c.style.cssText='visibility:visible!important;display:block!important;position:fixed!important;left:50%!important;top:50%!important;width:680px!important;height:470px!important;max-width:none!important;max-height:none!important;transform:translate(-50%,-50%) scale(.49)!important;transform-origin:center!important;background:transparent!important;pointer-events:none!important';
                return true;
              };
              let n=0,t=setInterval(()=>{if(pick()||++n>160)clearInterval(t)},125); pick();
              window.__portraitRotate=dx=>{
                const c=window.__portraitCanvas;if(!c)return;
                const r=c.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                const ev=(t,xx)=>new PointerEvent(t,{pointerId:77,pointerType:'mouse',isPrimary:true,bubbles:true,cancelable:true,clientX:xx,clientY:y,buttons:t==='pointerup'?0:1,button:0});
                c.dispatchEvent(ev('pointerdown',x));c.dispatchEvent(ev('pointermove',x+dx));c.dispatchEvent(ev('pointerup',x+dx));
              };
            })();
            """
            webView.evaluateJavaScript(js)
        }

        @objc func pan(_ g: UIPanGestureRecognizer) {
            guard let w=webView else{return}
            let x=g.translation(in:w).x
            if g.state == .began { lastX=x; return }
            let dx=x-lastX; lastX=x
            if abs(dx)>0.1 { w.evaluateJavaScript("window.__portraitRotate&&window.__portraitRotate(\(Double(dx)*2));") }
        }
    }

    func makeUIView(context: Context) -> WKWebView {
        let cfg=WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        let w=WKWebView(frame:.zero,configuration:cfg)
        w.isOpaque=false; w.backgroundColor=.clear; w.scrollView.backgroundColor=.clear; w.scrollView.isScrollEnabled=false
        w.navigationDelegate=context.coordinator; context.coordinator.webView=w
        if let u=URL(string:"https://kintara.com/play") {
            var r=URLRequest(url:u,cachePolicy:.returnCacheDataElseLoad)
            r.setValue(cookie,forHTTPHeaderField:"Cookie")
            w.load(r)
        }
        let pan=UIPanGestureRecognizer(target:context.coordinator,action:#selector(Coordinator.pan(_:)))
        w.addGestureRecognizer(pan)
        return w
    }

    func updateUIView(_ w: WKWebView, context: Context) {
        context.coordinator.webView=w
        context.coordinator.isolate(w)
    }
}
