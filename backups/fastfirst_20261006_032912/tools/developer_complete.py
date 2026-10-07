import subprocess
import sys
from pathlib import Path
import re


class DeveloperTool:
    name = "developer"
    description = "Project engineering tool for code search, editing, testing and diagnostics inside KAREEM_AGENT workspace."

    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()

    def _safe(self, path):
        p = (self.workspace / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if self.workspace != p and self.workspace not in p.parents:
            raise PermissionError("DeveloperTool can only modify files inside the agent workspace.")
        return p

    def project_tree(self, max_depth=3):
        rows=[]
        for p in self.workspace.rglob('*'):
            rel=p.relative_to(self.workspace)
            if len(rel.parts)>max_depth or any(x in rel.parts for x in ['.venv','agent_memory','__pycache__','.git']): continue
            rows.append({'path':str(rel),'type':'dir' if p.is_dir() else 'file'})
        return {'success':True,'items':rows[:2000]}

    def search_code(self, pattern, extensions=None, max_results=100):
        exts=set(extensions or ['.py','.ps1','.bat','.md','.json','.js','.ts','.html'])
        rg=None
        try:
            cp=subprocess.run(['rg','-n','--hidden','-g', '!.venv/**','-g','!.git/**',pattern,str(self.workspace)],capture_output=True,text=True,timeout=30)
            if cp.returncode in (0,1):
                lines=cp.stdout.splitlines()[:max_results]
                return {'success':True,'matches':lines}
        except Exception:
            pass
        out=[]
        rx=re.compile(pattern,re.I)
        for p in self.workspace.rglob('*'):
            if len(out)>=max_results or not p.is_file() or p.suffix.lower() not in exts or any(x in p.parts for x in ['.venv','.git','__pycache__']): continue
            try: text=p.read_text(encoding='utf-8',errors='ignore')
            except Exception: continue
            for i,line in enumerate(text.splitlines(),1):
                if rx.search(line): out.append(f'{p.relative_to(self.workspace)}:{i}:{line}')
                if len(out)>=max_results: break
        return {'success':True,'matches':out}

    def read_code(self, path, start_line=1, max_lines=400):
        p=self._safe(path)
        if not p.is_file(): return {'success':False,'error':'File not found'}
        lines=p.read_text(encoding='utf-8',errors='ignore').splitlines()
        start=max(1,int(start_line)); end=min(len(lines),start+int(max_lines)-1)
        return {'success':True,'path':str(p),'start_line':start,'end_line':end,'content':'\n'.join(lines[start-1:end])}

    def write_code(self, path, content, backup=True):
        p=self._safe(path); p.parent.mkdir(parents=True,exist_ok=True)
        backup_path=None
        if p.exists() and backup:
            backup_path=p.with_suffix(p.suffix+'.bak_complete')
            backup_path.write_bytes(p.read_bytes())
        p.write_text(content,encoding='utf-8')
        return {'success':True,'path':str(p),'backup':str(backup_path) if backup_path else None}

    def run_tests(self, test_args='-q', timeout=180):
        cmd=[sys.executable,'-m','pytest',*str(test_args).split()]
        cp=subprocess.run(cmd,cwd=self.workspace,capture_output=True,text=True,timeout=int(timeout))
        return {'success':cp.returncode==0,'exit_code':cp.returncode,'stdout':cp.stdout[-20000:],'stderr':cp.stderr[-10000:]}

    def run_python(self, path, args=None, timeout=120):
        p=self._safe(path)
        cp=subprocess.run([sys.executable,str(p),*(args or [])],cwd=self.workspace,capture_output=True,text=True,timeout=int(timeout))
        return {'success':cp.returncode==0,'exit_code':cp.returncode,'stdout':cp.stdout[-20000:],'stderr':cp.stderr[-10000:]}

    def git_status(self):
        cp=subprocess.run(['git','status','--short'],cwd=self.workspace,capture_output=True,text=True,timeout=20)
        return {'success':cp.returncode==0,'stdout':cp.stdout,'stderr':cp.stderr}

    def git_diff(self):
        cp=subprocess.run(['git','diff','--','.'],cwd=self.workspace,capture_output=True,text=True,timeout=30)
        return {'success':cp.returncode==0,'stdout':cp.stdout[-30000:],'stderr':cp.stderr[-5000:]}

    def describe(self):
        return {'name':self.name,'description':self.description,'actions':{
            'project_tree':{'description':'Inspect the project structure.','parameters':{'max_depth':{'type':'integer','required':False}}},
            'search_code':{'description':'Search source files by text or regex.','parameters':{'pattern':{'type':'string','required':True},'extensions':{'type':'array','required':False},'max_results':{'type':'integer','required':False}}},
            'read_code':{'description':'Read a bounded source-file range.','parameters':{'path':{'type':'string','required':True},'start_line':{'type':'integer','required':False},'max_lines':{'type':'integer','required':False}}},
            'write_code':{'description':'Write a source file inside the agent workspace; creates a backup by default.','parameters':{'path':{'type':'string','required':True},'content':{'type':'string','required':True},'backup':{'type':'boolean','required':False}}},
            'run_tests':{'description':'Run the project pytest suite.','parameters':{'test_args':{'type':'string','required':False},'timeout':{'type':'integer','required':False}}},
            'run_python':{'description':'Run a Python file inside the workspace.','parameters':{'path':{'type':'string','required':True},'args':{'type':'array','required':False},'timeout':{'type':'integer','required':False}}},
            'git_status':{'description':'Inspect working-tree changes.','parameters':{}},
            'git_diff':{'description':'Inspect current code diff.','parameters':{}},
        }}
