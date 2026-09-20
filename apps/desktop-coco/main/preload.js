const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('coco', {
  getConf: () => ipcRenderer.invoke('conf:get'),
  setConf: (o) => ipcRenderer.invoke('conf:set', o),
  openExternal: (u) => ipcRenderer.invoke('open:external', u),
});
