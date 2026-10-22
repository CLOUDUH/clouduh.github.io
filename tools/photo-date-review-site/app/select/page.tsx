'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ChevronLeft, ChevronRight, Download, FolderCheck, Heart, ImageOff, Pin, RefreshCw, Upload } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';

type Photo = { id: string; relativePath: string; filename: string; subfolder: string; modified: string; preview: string | null };
type ExistingPick = { id: string; relativePath: string; filename: string; preview: string | null; matchedPhotoId: string | null };
type Folder = { id: string; event: string; count: number; existingCount: number; initialSelectedIds: string[]; existingPicks: ExistingPick[]; photos: Photo[] };
type Manifest = { version: number; generatedAt: string; folderCount: number; totalPhotos: number; existingFavorites: number; missingPreviews: number; folders: Folder[] };

const STORAGE_KEY = 'photo-favorite-picker-all-v3';

function sized(url: string | null, size: number) {
  if (!url) return null;
  return `${url}${url.includes('?') ? '&' : '?'}size=${size}`;
}

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}

export default function FavoritePickerPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [activeFolderId, setActiveFolderId] = useState('');
  const [photoIndex, setPhotoIndex] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');
  const importRef = useRef<HTMLInputElement>(null);
  const folderButtons = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    fetch(`/favorite-picker/manifest.json?v=${Date.now()}`, { cache: 'no-store' })
      .then((response) => { if (!response.ok) throw new Error('无法读取全部照片清单'); return response.json(); })
      .then((data: Manifest) => {
        setManifest(data);
        let cached: { selectedIds?: string[]; completedFolderIds?: string[]; activeFolderId?: string } = {};
        try { cached = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}'); } catch { cached = {}; }
        const existing = data.folders.flatMap((folder) => folder.initialSelectedIds);
        setSelected(new Set([...existing, ...(cached.selectedIds ?? [])]));
        setCompleted(new Set(cached.completedFolderIds ?? []));
        const cachedFolder = data.folders.some((folder) => folder.id === cached.activeFolderId) ? cached.activeFolderId : '';
        setActiveFolderId(cachedFolder || data.folders[0]?.id || '');
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : '加载失败'));
  }, []);

  useEffect(() => {
    if (!manifest) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ selectedIds: [...selected], completedFolderIds: [...completed], activeFolderId }));
  }, [manifest, selected, completed, activeFolderId]);

  const folder = manifest?.folders.find((item) => item.id === activeFolderId) ?? manifest?.folders[0];
  const folderIndex = manifest && folder ? manifest.folders.findIndex((item) => item.id === folder.id) : 0;
  const boundedIndex = folder ? Math.min(photoIndex, Math.max(0, folder.photos.length - 1)) : 0;
  const photo = folder?.photos[boundedIndex];
  const existingMatched = useMemo(() => new Set(folder?.initialSelectedIds ?? []), [folder]);
  const newPicks = useMemo(() => folder?.photos.filter((item) => selected.has(item.id) && !existingMatched.has(item.id)) ?? [], [folder, selected, existingMatched]);
  const filmstrip = useMemo(() => {
    if (!folder) return [];
    const start = Math.max(0, boundedIndex - 8); const end = Math.min(folder.photos.length, boundedIndex + 9);
    return folder.photos.slice(start, end).map((item, offset) => ({ item, index: start + offset }));
  }, [folder, boundedIndex]);
  const totalNewPicks = useMemo(() => {
    if (!manifest) return 0;
    const initial = new Set(manifest.folders.flatMap((item) => item.initialSelectedIds));
    return [...selected].filter((id) => !initial.has(id)).length;
  }, [manifest, selected]);

  useEffect(() => { if (folder) folderButtons.current[folder.id]?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' }); }, [folder]);

  function selectFolder(id: string) { setActiveFolderId(id); setPhotoIndex(0); }
  function moveFolder(step: number) {
    if (!manifest || !folder) return;
    const next = (folderIndex + step + manifest.folders.length) % manifest.folders.length;
    selectFolder(manifest.folders[next].id);
  }
  function movePhoto(step: number) {
    if (!folder?.photos.length) return;
    setPhotoIndex((current) => Math.max(0, Math.min(folder.photos.length - 1, current + step)));
  }
  function toggleCurrent() {
    if (!photo || existingMatched.has(photo.id)) return;
    setSelected((current) => { const next = new Set(current); if (next.has(photo.id)) next.delete(photo.id); else next.add(photo.id); return next; });
  }
  function toggleComplete() {
    if (!folder) return;
    setCompleted((current) => { const next = new Set(current); if (next.has(folder.id)) next.delete(folder.id); else next.add(folder.id); return next; });
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input,textarea,select,[role="combobox"]')) return;
      if (event.key === 'ArrowLeft') { event.preventDefault(); movePhoto(-1); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); movePhoto(1); }
      else if (event.key === '-') { event.preventDefault(); moveFolder(-1); }
      else if (event.key === '=' || event.key === '+') { event.preventDefault(); moveFolder(1); }
      else if (event.key.toLowerCase() === 'p' || event.code === 'Space') { event.preventDefault(); toggleCurrent(); }
    }
    window.addEventListener('keydown', onKeyDown); return () => window.removeEventListener('keydown', onKeyDown);
  });

  function exportJson() {
    if (!manifest) return;
    const initial = new Set(manifest.folders.flatMap((item) => item.initialSelectedIds));
    const allPhotos = manifest.folders.flatMap((item) => item.photos.map((photoItem) => ({ ...photoItem, event: item.event, folderId: item.id })));
    const selectedPhotos = allPhotos.filter((item) => selected.has(item.id));
    download('photo-favorite-selection-all.json', JSON.stringify({
      version: 2, exportedAt: new Date().toISOString(), sourceGeneratedAt: manifest.generatedAt,
      totalFolders: manifest.folderCount, completedFolders: [...completed], selectedCount: selectedPhotos.length,
      newSelectedCount: selectedPhotos.filter((item) => !initial.has(item.id)).length,
      selectedPhotos, newSelectedPhotos: selectedPhotos.filter((item) => !initial.has(item.id)),
      existingFavorites: manifest.folders.flatMap((item) => item.existingPicks.map((pick) => ({ ...pick, event: item.event }))),
    }, null, 2));
  }

  async function importJson(file?: File) {
    if (!file || !manifest) return;
    try {
      const payload = JSON.parse(await file.text());
      const existing = manifest.folders.flatMap((item) => item.initialSelectedIds);
      const ids = (payload.selectedPhotos ?? payload.newSelectedPhotos ?? []).map((item: { id: string }) => item.id);
      setSelected(new Set([...existing, ...ids])); setCompleted(new Set(payload.completedFolders ?? []));
    } catch { window.alert('无法导入该文件，请确认它由本页面导出。'); }
  }

  if (error) return <main className="grid min-h-screen place-items-center p-8 text-destructive">{error}</main>;
  if (!manifest || !folder) return <main className="min-h-screen animate-pulse bg-background" />;
  const picked = photo ? selected.has(photo.id) : false;
  const alreadyExisting = photo ? existingMatched.has(photo.id) : false;

  return <main className="min-h-screen bg-background text-foreground">
    <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur-xl"><div className="mx-auto flex max-w-[1800px] items-center gap-4 px-4 py-3 lg:px-7"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><Heart className="size-5 fill-primary text-primary"/><h1 className="font-semibold">全相册精选工作台</h1><Badge variant="outline">本机私密 · 无磁盘图片缓存</Badge><span className="text-xs text-muted-foreground">已有 {manifest.existingFavorites} · 新选 {totalNewPicks}</span></div><Progress value={(completed.size/manifest.folderCount)*100} className="mt-2 max-w-xl"><ProgressLabel>文件夹进度</ProgressLabel><ProgressValue>{completed.size}/{manifest.folderCount}</ProgressValue></Progress></div><div className="hidden gap-2 sm:flex"><Button variant="ghost" onClick={()=>window.location.reload()}><RefreshCw/>刷新清单</Button><Button variant="outline" onClick={()=>importRef.current?.click()}><Upload/>导入</Button><Button onClick={exportJson}><Download/>导出选择</Button></div><input ref={importRef} type="file" accept="application/json" className="hidden" onChange={(event)=>importJson(event.target.files?.[0])}/></div></header>

    <nav className="sticky top-[73px] z-30 border-b bg-background/96 px-3 py-2 backdrop-blur-xl lg:px-6"><div className="flex gap-2 overflow-x-auto pb-1">{manifest.folders.map((item,index)=>{const newCount=item.photos.filter((entry)=>selected.has(entry.id)&&!item.initialSelectedIds.includes(entry.id)).length;return <button key={item.id} ref={(element)=>{folderButtons.current[item.id]=element;}} onClick={()=>selectFolder(item.id)} className={`min-w-max rounded-xl border px-3 py-2 text-left transition ${item.id===folder.id?'border-primary bg-primary text-primary-foreground shadow-sm':'bg-card hover:bg-muted'}`}><div className="flex items-center gap-2 text-xs font-medium"><span className="opacity-60">{index+1}</span>{item.event}{completed.has(item.id)&&<CheckCircle2 className="size-3.5"/>}</div><p className={`mt-0.5 text-[10px] ${item.id===folder.id?'text-primary-foreground/75':'text-muted-foreground'}`}>{item.count} 张 · 已有 {item.existingCount} · 新选 {newCount}</p></button>;})}</div></nav>

    <div className="mx-auto max-w-[1800px] space-y-4 p-3 lg:p-6">
      <section className="rounded-2xl border bg-card p-3 shadow-sm"><div className="mb-2 flex items-center justify-between gap-3"><div className="flex items-center gap-2"><Pin className="size-4 text-primary"/><h2 className="text-sm font-semibold">{folder.event} · 已 Pin 精选</h2><Badge variant="secondary">已有 {folder.existingPicks.length} · 本轮 {newPicks.length}</Badge></div><Button size="sm" variant={completed.has(folder.id)?'secondary':'outline'} onClick={toggleComplete}>{completed.has(folder.id)?<CheckCircle2/>:<FolderCheck/>}{completed.has(folder.id)?'本文件夹已完成':'标记完成'}</Button></div>
        <div className="flex min-h-24 gap-2 overflow-x-auto rounded-xl bg-muted/30 p-2">{folder.existingPicks.map((item)=><div key={item.id} className="w-28 shrink-0 overflow-hidden rounded-lg border bg-background"><div className="relative h-20 bg-photo-stage">{item.preview?<img src={sized(item.preview,280)??''} alt={item.filename} loading="lazy" className="h-full w-full object-cover"/>:<ImageOff className="m-auto text-stone-400"/>}<Badge className="absolute left-1 top-1 h-4 px-1 text-[9px]">已有</Badge></div><p className="truncate px-1.5 py-1 text-[10px]" title={item.filename}>{item.filename}</p></div>)}{newPicks.map((item)=><button key={item.id} onClick={()=>setPhotoIndex(folder.photos.findIndex((entry)=>entry.id===item.id))} className="w-28 shrink-0 overflow-hidden rounded-lg border border-primary bg-background text-left ring-1 ring-primary/20"><div className="relative h-20 bg-photo-stage">{item.preview?<img src={sized(item.preview,280)??''} alt={item.filename} loading="lazy" className="h-full w-full object-cover"/>:<ImageOff className="m-auto text-stone-400"/>}<Badge className="absolute left-1 top-1 h-4 px-1 text-[9px]">本轮</Badge></div><p className="truncate px-1.5 py-1 text-[10px]" title={item.filename}>{item.filename}</p></button>)}{folder.existingPicks.length===0&&newPicks.length===0&&<div className="grid w-full place-items-center text-xs text-muted-foreground">这个文件夹还没有精选照片</div>}</div></section>

      <section className="overflow-hidden rounded-3xl border bg-card shadow-sm"><div className="grid lg:grid-cols-[minmax(0,1fr)_340px]"><div className="relative grid min-h-[58vh] place-items-center bg-photo-stage p-3 lg:min-h-[66vh]">{photo?.preview?<img key={photo.id} src={sized(photo.preview,1800)??''} alt={photo.filename} className="max-h-[64vh] max-w-full object-contain"/>:<ImageOff className="size-12 text-stone-400"/>}<Badge className="absolute left-3 top-3 bg-black/65 text-white">{boundedIndex+1}/{folder.photos.length}</Badge></div>
        <aside className="flex flex-col p-5"><p className="text-xs font-medium uppercase tracking-[.12em] text-muted-foreground">文件夹 {folderIndex+1}/{manifest.folderCount}</p><h2 className="mt-2 break-all text-lg font-semibold">{photo?.filename}</h2><p className="mt-1 break-all text-xs text-muted-foreground">{photo?.relativePath}</p>{photo?.subfolder&&<Badge variant="outline" className="mt-3 w-fit">子目录：{photo.subfolder}</Badge>}<div className="mt-6 rounded-2xl border bg-muted/35 p-3 text-sm">{alreadyExisting?<p className="flex items-center gap-2 font-medium text-primary"><CheckCircle2 className="size-4"/>根目录已有这张精选</p>:picked?<p className="flex items-center gap-2 font-medium text-primary"><Pin className="size-4"/>已加入本轮 Pin</p>:<p className="text-muted-foreground">按 P 或空格把当前照片加入 Pin</p>}</div><Button className="mt-4 h-12" variant={picked?'default':'outline'} disabled={alreadyExisting||!photo} onClick={toggleCurrent}><Heart className={picked?'fill-current':''}/>{alreadyExisting?'已经是精选':picked?'取消 Pick':'Pick 当前照片'}</Button><div className="mt-auto space-y-3 pt-6"><div className="grid grid-cols-2 gap-2"><Button variant="outline" disabled={boundedIndex===0} onClick={()=>movePhoto(-1)}><ChevronLeft/>上一张</Button><Button disabled={boundedIndex>=folder.photos.length-1} onClick={()=>movePhoto(1)}>下一张<ChevronRight/></Button></div><div className="grid grid-cols-2 gap-2"><Button variant="ghost" onClick={()=>moveFolder(-1)}>- 上个文件夹</Button><Button variant="ghost" onClick={()=>moveFolder(1)}>= 下个文件夹</Button></div><p className="text-center text-[11px] leading-5 text-muted-foreground">← / → 切照片 · P / 空格 Pick · - / = 切文件夹</p></div></aside></div>
        <div className="border-t bg-muted/20 p-2"><div className="flex justify-center gap-2 overflow-x-auto py-1">{filmstrip.map(({item,index})=><button key={item.id} onClick={()=>setPhotoIndex(index)} className={`relative h-20 w-28 shrink-0 overflow-hidden rounded-lg border-2 bg-photo-stage ${index===boundedIndex?'border-primary ring-2 ring-primary/25':'border-transparent opacity-75 hover:opacity-100'}`}>{item.preview?<img src={sized(item.preview,260)??''} alt={item.filename} loading="lazy" className="h-full w-full object-cover"/>:<ImageOff className="m-auto text-stone-400"/>}{selected.has(item.id)&&<span className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-primary text-primary-foreground"><Heart className="size-3 fill-current"/></span>}</button>)}</div></div>
      </section>
    </div>
  </main>;
}
