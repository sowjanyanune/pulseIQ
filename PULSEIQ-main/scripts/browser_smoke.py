from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'exports'/'browser_qa'
OUT.mkdir(parents=True,exist_ok=True)
BASE_URL='http://127.0.0.1:8511'
def exercise():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1100})
        page.set_default_timeout(15000)
        page.goto(BASE_URL,wait_until='networkidle')
        page.get_by_role('heading',name='Student success, with a clear next step').wait_for()
        page.locator('[data-testid=stPlotlyChart] .js-plotly-plot').first.wait_for()
        page.locator('[data-testid=stDataFrame] canvas').first.wait_for()
        page.screenshot(path=str(OUT/'overview.png'),full_page=True)
        page.get_by_test_id('stSidebar').get_by_text('Student Profile',exact=True).click()
        page.get_by_role('heading',name='Student Profile',exact=True).wait_for()
        page.get_by_text('68.0',exact=True).wait_for()
        page.locator('[data-testid=stPlotlyChart] .js-plotly-plot').first.wait_for()
        page.screenshot(path=str(OUT/'profile.png'),full_page=True)
        page.get_by_test_id('stSidebar').get_by_text('Import & data quality',exact=True).click()
        page.get_by_role('heading',name='Import & data quality',exact=True).wait_for()
        for source in ['students','academic']:
            uploader=page.get_by_test_id('stFileUploader').filter(has=page.get_by_text(source+'.csv',exact=True))
            uploader.locator('input[type=file]').set_input_files(str(ROOT/'fixtures'/'invalid'/(source+'.csv')))
        page.get_by_text('I confirm these are synthetic or appropriately de-identified demonstration records.',exact=True).click()
        page.get_by_role('button',name='Validate and activate files',exact=True).click()
        page.get_by_text('Import blocked. Fix the errors below and upload again. The previous dataset is still active.').wait_for()
        assert page.get_by_text('Synthetic college demo · 200 students',exact=True).count()>0
        page.screenshot(path=str(OUT/'invalid_import.png'),full_page=True)
        for source in ['students','academic','attendance','lms','placement','skills','engagement','feedback']:
            uploader=page.get_by_test_id('stFileUploader').filter(has=page.get_by_text(source+'.csv',exact=True))
            uploader.locator('input[type=file]').set_input_files(str(ROOT/'demo_data'/(source+'.csv')))
        page.get_by_role('button',name='Validate and activate files',exact=True).click()
        page.get_by_text('Uploaded demonstration files',exact=True).wait_for()
        page.get_by_test_id('stSidebar').get_by_text('Student Profile',exact=True).click()
        page.get_by_role('heading',name='Student Profile',exact=True).wait_for()
        page.get_by_text('68.0',exact=True).wait_for()
        # Custom faculty action: check input and create in the actual browser.
        page.get_by_role('textbox',name='Owner alias',exact=True).fill('Browser Mentor')
        page.get_by_role('textbox',name='Editable action',exact=True).fill('Schedule coding practice.')
        page.get_by_role('button',name='Create support action',exact=True).click()
        page.get_by_text('Action created. Review it on the Action Board and export your session records.').wait_for()
        page.get_by_test_id('stSidebar').get_by_text('Action Board',exact=True).click()
        page.get_by_role('heading',name='Action Board',exact=True).wait_for()
        page.get_by_role('button',name='Export visible actions CSV',exact=True).wait_for()
        with page.expect_download() as event:
            page.get_by_role('button',name='Export visible actions CSV',exact=True).click()
        downloaded=event.value
        downloaded.save_as(str(OUT/'downloaded_actions.csv'))
        assert 'Browser Mentor' in (OUT/'downloaded_actions.csv').read_text(encoding='utf-8-sig')
        with page.expect_download() as event:
            page.get_by_role('button',name='Export action revision history CSV',exact=True).click()
        event.value.save_as(str(OUT/'downloaded_history.csv'))
        page.screenshot(path=str(OUT/'action_board.png'),full_page=True)
        # Independent browser context has fresh demo and no uploaded records/actions.
        other=browser.new_context(viewport={'width':1440,'height':1000})
        separate=other.new_page()
        separate.goto(BASE_URL,wait_until='networkidle')
        separate.get_by_role('heading',name='Student success, with a clear next step').wait_for()
        separate.get_by_test_id('stSidebar').get_by_text('Action Board',exact=True).click()
        separate.get_by_text('No actions match these filters. Create one from a Student Profile, or adjust your filters.').wait_for()
        page.get_by_test_id('stSidebar').get_by_text('Overview',exact=True).click()
        page.get_by_role('heading',name='Student success, with a clear next step').wait_for()
        with page.expect_download() as event:
            page.get_by_role('button',name='Download cohort evidence CSV',exact=True).click()
        event.value.save_as(str(OUT/'downloaded_cohort.csv'))
        assert len((OUT/'downloaded_cohort.csv').read_text(encoding='utf-8-sig').splitlines())==201
        # Mobile rendering and overflow check.
        mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,device_scale_factor=1)
        mp=mobile.new_page();mp.goto(BASE_URL,wait_until='networkidle')
        mp.get_by_role('heading',name='Student success, with a clear next step').wait_for()
        mp.locator('[data-testid=stPlotlyChart] .js-plotly-plot').first.wait_for()
        mp.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        assert mp.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
        assert page.get_by_test_id('stException').count()==0
        print('PASS: desktop/mobile render, invalid+valid eight-file upload, action creation, action/history/cohort downloads, independent sessions; no page overflow.')
        browser.close()

if __name__=='__main__':
    import subprocess,sys,time,urllib.request
    with (OUT/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.port','8511','--server.address','127.0.0.1'],cwd=ROOT,stdout=log,stderr=log)
        try:
            ready=False
            for _ in range(40):
                if server.poll() is not None:
                    raise RuntimeError('Server could not start. Port 8511 must be free; inspect exports/browser_qa/server.log.')
                try:
                    urllib.request.urlopen(BASE_URL+'/_stcore/health',timeout=1)
                    ready=True
                    break
                except Exception:
                    time.sleep(.25)
            if not ready:
                raise RuntimeError('Local server did not become ready.')
            exercise()
        finally:
            server.terminate()
            server.wait(timeout=10)
