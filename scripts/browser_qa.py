#!/usr/bin/env python3
"""Optional real-Chromium QA + PNG export. Requires playwright and a local browser.
No browser downloads, installs, servers, or external requests are made by this script.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('html',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--browser',help='Path to an existing Chromium/Chrome executable')
    args=ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Install Playwright in your approved environment or use an available browser manually. No PNG generated.',file=sys.stderr)
        return 2
    args.out.mkdir(parents=True,exist_ok=True)
    executable=args.browser or shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
    log={'browser':'Chromium','load_method':'set_content (self-contained HTML; no file URL navigation tested)','checks':[], 'screenshots':[], 'limitations':['Checks model topology, geometry and UI, not the semantic correctness of arbitrary rule strings or real project code.','PNG appearance uses local fallback fonts; no font files are bundled.']}
    def check(name,passed,details=None):
        entry={'check':name,'passed':bool(passed)}
        if details is not None:entry['details']=details
        log['checks'].append(entry)
    with sync_playwright() as p:
        launch={'headless':True}
        if executable:launch['executable_path']=executable
        try:browser=p.chromium.launch(**launch)
        except Exception as e:
            print('No usable local Chromium. Supply --browser PATH. '+str(e).splitlines()[0],file=sys.stderr)
            return 2
        page=browser.new_page(viewport={'width':2180,'height':1550},device_scale_factor=1)
        errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append(r.url))
        page.route('**/*',lambda route:route.abort())
        page.set_content(args.html.read_text(encoding='utf-8'),wait_until='load')
        page.wait_for_function("document.documentElement.dataset.ready==='true'")
        check('no JavaScript errors',not errors,errors)
        check('no external resource requests',not requests,requests)
        report=page.evaluate('window.lineage.report')
        check('rendered field/edge counts match validated model',page.locator('.field').count()==report['fields'] and page.locator('.dep').count()==report['dependency_edges'])
        # Trace every exposed output; assert rendered highlighted edges are exactly the computed graph edges.
        for ref in report['outputs']:
            page.evaluate('(ref)=>window.lineage.select(ref)',ref)
            js=page.evaluate('(ref)=>window.lineage.trace(ref)',ref)
            expected=report['traces'][ref]
            highlighted=page.locator('.dep.on').count()
            check('trace '+ref,set(js['fields'])==set(expected['fields']) and set(js['roots'])==set(expected['roots']) and highlighted==len(expected['edges']))
        default=page.evaluate('window.lineage.model.default_field || window.lineage.report.outputs.at(-1)')
        page.evaluate('(r)=>window.lineage.select(r)',default)
        page.locator('.shell').screenshot(path=str(args.out/'focus.png'))
        log['screenshots'].append('focus.png')
        page.evaluate("window.lineage.setMode('all')")
        page.locator('.shell').screenshot(path=str(args.out/'overview.png'))
        page.locator('#lineage-svg').screenshot(path=str(args.out/'diagram.png'))
        log['screenshots']+=['overview.png','diagram.png']
        # Detect edges crossing unrelated cards by sampling SVG path geometry.
        crossings=page.evaluate('''() => {
          const boxes=window.lineage.report.geometry.boxes, bad=[];
          for(const path of document.querySelectorAll('.dep')){
            const a=path.dataset.source.split('.')[0],b=path.dataset.target.split('.')[0],len=path.getTotalLength();
            for(const [id,box] of Object.entries(boxes)){
              if(id===a||id===b)continue;let hit=false;
              for(let v=0;v<=len;v+=3){const pt=path.getPointAtLength(v);if(pt.x>box.x+2&&pt.x<box.x+box.w-2&&pt.y>box.y+2&&pt.y<box.y+box.h-2){hit=true;break;}}
              if(hit)bad.push(path.dataset.source+' -> '+path.dataset.target+' crosses '+id);
            }
          } return bad;
        }''')
        check('dependency edges do not cross unrelated node boxes',not crossings,crossings)
        # Text is width-fitted; check geometrical overflow from its owning node.
        overflow=page.evaluate('''() => {const bad=[];for(const n of document.querySelectorAll('.node')){const box=window.lineage.report.geometry.boxes[n.dataset.node];for(const text of n.querySelectorAll('text')){const r=text.getBBox();if(r.x<box.x-1||r.x+r.width>box.x+box.w+1||r.y<box.y-1||r.y+r.height>box.y+box.h+1)bad.push(text.textContent);}}return bad;}''')
        check('node labels stay within card bounds',not overflow,overflow)
        # Actual click/keyboard interaction on a field, not only API calls.
        first=page.locator('.field').first
        ref=first.get_attribute('data-field')
        first.click();check('click selects exact field',page.locator('html').get_attribute('data-selected')==ref)
        first.focus();page.keyboard.press('Enter');check('keyboard field selection',page.locator('html').get_attribute('data-selected')==ref)
        search_term=page.evaluate('window.lineage.model.nodes[0].fields[0].label')
        page.locator('#search').fill(search_term)
        check('Chinese field search',page.locator('#search-list button').count()>0)
        page.locator('#search').fill('')
        for mode in ('flow','all','focus'):
            page.locator(f'[data-mode="{mode}"]').click()
            check('view mode '+mode,page.locator('html').get_attribute('data-mode')==mode)
        old=page.locator('#zoom-label').inner_text();page.locator('#zoom-in').click()
        check('zoom controls respond',page.locator('#zoom-label').inner_text()!=old)
        page.locator('#fit').click()
        with page.expect_download() as dl:page.locator('#export-svg').click()
        download=dl.value;download.save_as(str(args.out/'exported.svg'))
        check('SVG export', (args.out/'exported.svg').read_text().startswith('<svg'))
        with page.expect_download() as dl:page.locator('#export-json').click()
        dl.value.save_as(str(args.out/'exported-model.json'))
        check('JSON export',json.loads((args.out/'exported-model.json').read_text())==page.evaluate('window.lineage.model'))
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(300)
        page.evaluate('(r)=>window.lineage.select(r)',default)
        # On phones the diagram remains scrollable, not squeezed into unreadable text.
        page.locator('#fit').click()
        page.screenshot(path=str(args.out/'mobile.png'),full_page=True)
        log['screenshots'].append('mobile.png')
        check('mobile selected field is visible in scrollable canvas',page.evaluate('''() => {const c=document.querySelector('.canvas').getBoundingClientRect(),r=document.querySelector('.field.selected').getBoundingClientRect();return r.right>c.left && r.left<c.right && r.bottom>c.top && r.top<c.bottom;}'''))
        check('mobile document has no page-level horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        check('mobile inspector stacked below canvas',page.evaluate('document.querySelector(".inspector").getBoundingClientRect().top>=document.querySelector(".canvas").getBoundingClientRect().bottom-1'))
        log['browser_version']=browser.version
        check('no JavaScript errors after interactions',not errors,errors)
        browser.close()
    log['passed']=all(x['passed'] for x in log['checks'])
    (args.out/'qa.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':log['passed'],'checks':len(log['checks']),'failed':[x for x in log['checks'] if not x['passed']]},ensure_ascii=False,indent=2))
    return 0 if log['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
