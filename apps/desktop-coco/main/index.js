const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');

// 配置存放：%APPDATA%/Coco/config.json
const CONF = path.join(app.getPath('userData'), 'config.json');
const readConf = () => { try { return JSON.parse(fs.readFileSync(CONF, 'utf8')); } catch { return {}; } };
const writeConf = (o) => { fs.mkdirSync(path.dirname(CONF), { recursive: true }); fs.writeFileSync(CONF, JSON.stringify(o, null, 2)); };

let win;
function createWindow() {
  win = new BrowserWindow({
    width: 1280, height: 820, minWidth: 960, minHeight: 640,
    title: 'Coco（可可）',
    backgroundColor: '#f5f5f7',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  win.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

// 渲染层与主进程之间的最小接口（模式选择、配置读写、打开外链）
ipcMain.handle('conf:get', () => readConf());
ipcMain.handle('conf:set', (_e, o) => { writeConf(o); return true; });
ipcMain.handle('open:external', (_e, url) => shell.openExternal(url));
