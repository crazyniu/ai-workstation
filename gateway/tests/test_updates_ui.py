"""Exercise the actual updates renderer using a minimal DOM, without network or browser."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for the renderer check')
class UpdateRenderingTests(unittest.TestCase):
    def test_failure_keeps_component_and_error_visible_without_install_button(self):
        source = (Path(__file__).resolve().parents[1]/'web/app.js').read_text()
        renderer = source[source.index('async function loadUpdates(){'):source.index('async function job(')]
        script = """
const navigation=1,currentPage='updates',names={mihomo:'Mihomo',adguard:'AdGuard'},componentIcons={},latestWebRelease=null;
const nodes={};
const $=key=>nodes[key]??= {children:[],replaceChildren(){this.children=[]},append(...x){this.children.push(...x)}};
const element=(tag,text)=>({tag,text,children:[],append(...x){this.children.push(...x)}});
const icon=x=>x,button=(...x)=>x;
const api=async()=>({components:{mihomo:{version:'v1'},adguard:{version:'v1'}},checked:{mihomo:{error:'fetch failed',available:true,latest:'v2'},adguard:{latest:'v2',available:true}},job:{status:'success'}});
""" + renderer + """
loadUpdates().then(()=>console.log(JSON.stringify({rows:$('#components').children,status:$('#upgrade-status').textContent,badge:$('#nav-update-badge').textContent})));
"""
        result = subprocess.run(['node','-'], input=script, text=True, capture_output=True, check=True)
        output = json.loads(result.stdout)
        self.assertEqual(len(output['rows']), 2)
        self.assertEqual(len(output['rows'][0]['children']), 2)
        self.assertEqual(len(output['rows'][1]['children']), 3)
        self.assertIn('fetch failed', output['status'])
        self.assertIn('fetch failed', output['rows'][0]['children'][1]['children'][1]['text'])
        self.assertEqual(output['badge'], '1')
