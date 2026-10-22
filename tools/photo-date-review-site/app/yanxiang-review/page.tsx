'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarCheck, CalendarX, Download, ImageOff, Plus, Search, Upload } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';

type Item = {
  id: string; relativePath: string; sourcePath: string; filename: string; folderDate: string;
  captureDate: string; dateSource: string; matchesFolderDate: boolean; preview: string;
};
type Manifest = { version: number; generatedAt: string; count: number; folderCount: number; mismatchCount: number; deletedIdDocuments: number; items: Item[] };
type Review = { tags: string[]; timeText: string; updatedAt: string };
type ExportRow = Item & Review;

const STORAGE_KEY = 'yanxiang-event-review-v1';
const SHORTCUTS = '1234567890qwertyuiop[]'.split('');
const COLORS = ['bg-sky-600', 'bg-emerald-600', 'bg-amber-600', 'bg-rose-600', 'bg-violet-600', 'bg-cyan-600', 'bg-orange-600', 'bg-fuchsia-600'];

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}

function sized(url: string, size: number) { return url.replace(/size=\d+/, `size=${size}`); }

export default function YanxiangReviewPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState('');
  const [filter, setFilter] = useState<'all' | 'untagged' | 'reviewed' | 'mismatch'>('all');
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const [error, setError] = useState('');
  const importRef = useRef<HTMLInputElement>(null);
  const folderButtons = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    fetch(`/yanxiang-review/manifest.json?v=${Date.now()}`, { cache: 'no-store' })
      .then((response) => { if (!response.ok) throw new Error('无法读取燕翔照片清单'); return response.json(); })
      .then(setManifest).catch((reason) => setError(reason instanceof Error ? reason.message : '加载失败'));
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
      setReviews(saved.reviews ?? {}); setTags(saved.tags ?? []);
    } catch { setReviews({}); setTags([]); }
  }, []);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify({ reviews, tags })); }, [reviews, tags]);

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (manifest?.items ?? []).filter((item) => {
      const review = reviews[item.id]; const reviewed = Boolean(review?.tags.length || review?.timeText.trim());
      const status = filter === 'all' || (filter === 'untagged' && !reviewed) || (filter === 'reviewed' && reviewed) || (filter === 'mismatch' && !item.matchesFolderDate);
      return status && (!needle || `${item.filename} ${item.folderDate} ${item.relativePath}`.toLowerCase().includes(needle));
    });
  }, [manifest, reviews, filter, query]);

  useEffect(() => setIndex(0), [filter, query]);
  const active = items[Math.min(index, Math.max(0, items.length - 1))];
  const review = active ? reviews[active.id] ?? { tags: [], timeText: '', updatedAt: '' } : { tags: [], timeText: '', updatedAt: '' };
  const reviewedCount = manifest?.items.filter((item) => { const value = reviews[item.id]; return Boolean(value?.tags.length || value?.timeText.trim()); }).length ?? 0;
  const folders = useMemo(() => {
    const grouped = new Map<string, { date: string; count: number; allMatch: boolean }>();
    for (const item of manifest?.items ?? []) {
      const current = grouped.get(item.folderDate) ?? { date: item.folderDate, count: 0, allMatch: true };
      current.count += 1; current.allMatch = current.allMatch && item.matchesFolderDate; grouped.set(item.folderDate, current);
    }
    return [...grouped.values()].sort((left, right) => left.date.localeCompare(right.date));
  }, [manifest]);

  useEffect(() => {
    if (!items.length) return;
    for (const next of items.slice(index + 1, index + 3)) { const image = new Image(); image.src = sized(next.preview, 900); }
  }, [items, index]);

  useEffect(() => {
    if (active) folderButtons.current[active.folderDate]?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }, [active?.folderDate]);

  function update(patch: Partial<Review>) {
    if (!active) return;
    setReviews((current) => ({ ...current, [active.id]: { ...(current[active.id] ?? { tags: [], timeText: '', updatedAt: '' }), ...patch, updatedAt: new Date().toISOString() } }));
  }
  function move(step: number) { setIndex((value) => Math.max(0, Math.min(items.length - 1, value + step))); }
  function toggleTag(tag: string) { const next = review.tags.includes(tag) ? review.tags.filter((value) => value !== tag) : [...review.tags, tag]; update({ tags: next }); }
  function addTag() { const value = newTag.trim(); if (!value) return; if (!tags.includes(value)) setTags((current) => [...current, value]); setNewTag(''); if (active && !review.tags.includes(value)) update({ tags: [...review.tags, value] }); }
  function jumpToFolder(date: string) {
    if (!manifest) return;
    setFilter('all'); setQuery('');
    setIndex(Math.max(0, manifest.items.findIndex((item) => item.folderDate === date)));
  }

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input,textarea')) return;
      if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1); return; }
      if (event.key === 'ArrowRight') { event.preventDefault(); move(1); return; }
      const shortcut = SHORTCUTS.indexOf(event.key.toLowerCase());
      if (shortcut >= 0 && tags[shortcut]) { event.preventDefault(); toggleTag(tags[shortcut]); }
    }
    window.addEventListener('keydown', keydown); return () => window.removeEventListener('keydown', keydown);
  });

  function exportJson() {
    if (!manifest) return;
    const rows: ExportRow[] = manifest.items.map((item) => ({ ...item, ...(reviews[item.id] ?? { tags: [], timeText: '', updatedAt: '' }) }));
    download('yanxiang-photo-review.json', JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), sourceGeneratedAt: manifest.generatedAt, tags, total: rows.length, reviewed: reviewedCount, items: rows }, null, 2));
  }
  async function importJson(file?: File) {
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text()); const next: Record<string, Review> = {};
      for (const item of payload.items ?? []) if (item.id) next[item.id] = { tags: item.tags ?? [], timeText: item.timeText ?? '', updatedAt: item.updatedAt ?? '' };
      setReviews(next); setTags(payload.tags ?? []);
    } catch { window.alert('无法导入该 JSON。'); }
  }

  if (error) return <main className="grid min-h-screen place-items-center p-8 text-destructive">{error}</main>;
  if (!manifest) return <main className="min-h-screen animate-pulse bg-background" />;

  return <main className="min-h-screen bg-background text-foreground">
    <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur-xl"><div className="mx-auto flex max-w-[1800px] items-center gap-4 px-4 py-3 lg:px-6"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><CalendarCheck className="size-5 text-primary"/><h1 className="font-semibold">燕翔照片事件归类</h1><Badge variant="outline">单图按需加载 · 无磁盘缩略图缓存</Badge><span className="text-xs text-muted-foreground">{manifest.count} 张 · {manifest.folderCount} 天</span></div><Progress value={manifest.count ? reviewedCount / manifest.count * 100 : 0} className="mt-2 max-w-xl"><ProgressLabel>已标注</ProgressLabel><ProgressValue>{reviewedCount}/{manifest.count}</ProgressValue></Progress></div><Button variant="outline" onClick={() => importRef.current?.click()}><Upload/>导入</Button><Button onClick={exportJson}><Download/>导出结果</Button><input ref={importRef} type="file" accept="application/json" className="hidden" onChange={(event) => importJson(event.target.files?.[0])}/></div></header>

    <nav className="sticky top-[73px] z-30 border-b bg-background/96 px-3 py-2 backdrop-blur-xl lg:px-6"><div className="flex gap-2 overflow-x-auto pb-1">{folders.map((folder) => {
      const activeFolder = active?.folderDate === folder.date;
      return <button key={folder.date} ref={(element) => { folderButtons.current[folder.date] = element; }} onClick={() => jumpToFolder(folder.date)} className={`min-w-max rounded-xl border px-3 py-2 text-left transition ${folder.allMatch ? activeFolder ? 'border-emerald-300 bg-emerald-700 text-white ring-2 ring-emerald-300/40' : 'border-emerald-300 bg-emerald-600 text-white hover:bg-emerald-700' : activeFolder ? 'border-red-300 bg-red-700 text-white ring-2 ring-red-300/40' : 'border-red-300 bg-red-600 text-white hover:bg-red-700'}`}><p className="text-xs font-semibold">{folder.date}</p><p className="mt-0.5 text-[10px] text-white/80">{folder.count} 张 · {folder.allMatch ? '日期一致' : '存在异常'}</p></button>;
    })}</div></nav>

    <div className="mx-auto grid max-w-[1800px] gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_540px] lg:p-6">
      <section className="overflow-hidden rounded-3xl border bg-card shadow-sm"><div className="relative grid min-h-[72vh] place-items-center bg-photo-stage p-3">{active ? <img key={active.id} src={active.preview} alt={active.filename} className="max-h-[74vh] max-w-full object-contain"/> : <ImageOff className="size-12 text-stone-400"/>}<Badge className="absolute left-3 top-3 bg-black/65 text-white">{items.length ? index + 1 : 0}/{items.length}</Badge></div><div className="flex items-center gap-2 border-t p-3"><Button variant="outline" disabled={index === 0} onClick={() => move(-1)}>← 上一张</Button><Button disabled={index >= items.length - 1} onClick={() => move(1)}>下一张 →</Button><div className="relative ml-auto min-w-56 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"/><Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名或日期"/></div></div></section>

      <aside className="space-y-4 lg:sticky lg:top-[150px] lg:self-start">
        <section className="rounded-2xl border bg-card p-4 shadow-sm"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-muted-foreground">当前照片</p><h2 className="mt-1 break-all font-semibold">{active?.filename ?? '无'}</h2></div>{active && (active.matchesFolderDate ? <Badge className="bg-emerald-600"><CalendarCheck/>日期一致</Badge> : <Badge variant="destructive"><CalendarX/>日期不一致</Badge>)}</div>{active && <div className="mt-3 grid gap-2 rounded-xl bg-muted/45 p-3 text-xs"><p><span className="text-muted-foreground">拍摄时间：</span><span className="font-mono">{active.captureDate}</span></p><p><span className="text-muted-foreground">当前文件夹：</span><span className="font-mono">{active.folderDate}</span></p><p><span className="text-muted-foreground">日期来源：</span>{active.dateSource}</p><p className="break-all text-muted-foreground">{active.relativePath}</p></div>}</section>

        <section className="rounded-2xl border bg-card p-4 shadow-sm"><div className="mb-2 flex items-center justify-between"><h3 className="font-semibold">事件标签</h3><Badge variant="secondary">已选 {review.tags.length}</Badge></div><div className="flex gap-2"><Input value={newTag} onChange={(event) => setNewTag(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') addTag(); }} placeholder="输入新标签，如：2019赛场"/><Button onClick={addTag}><Plus/>添加</Button></div><div className="mt-3 min-h-52 max-h-[38vh] overflow-y-auto rounded-xl border bg-muted/25 p-2"><div className="flex flex-wrap content-start gap-2">{tags.map((tag, tagIndex) => { const selected = review.tags.includes(tag); return <Button key={tag} type="button" size="sm" variant={selected ? 'default' : 'outline'} className={selected ? COLORS[tagIndex % COLORS.length] : ''} onClick={() => toggleTag(tag)}><span className="mr-1 font-mono text-[10px] opacity-70">{SHORTCUTS[tagIndex] ?? '·'}</span>{tag}</Button>; })}{tags.length === 0 && <p className="p-3 text-xs text-muted-foreground">添加标签后，标签会固定在这里并供所有照片复用。</p>}</div></div><p className="mt-2 text-[11px] text-muted-foreground">标签区域尺寸固定，不会随照片切换移动。前 22 个标签可用 1–0、Q–P、[ ] 快速选择。</p></section>

        <section className="rounded-2xl border bg-card p-4 shadow-sm"><h3 className="font-semibold">拍摄时间修正意见</h3><Textarea className="mt-2 min-h-28" value={review.timeText} onChange={(event) => update({ timeText: event.target.value })} placeholder="可随意输入，例如：应该是2019年11月21日下午、和上一张同一天……"/><p className="mt-2 text-[11px] text-muted-foreground">内容自动保存在本机浏览器。输入框聚焦时不会触发快捷键。</p></section>

        <section className="flex flex-wrap gap-2 rounded-2xl border bg-card p-3">{(['all', 'untagged', 'reviewed', 'mismatch'] as const).map((value) => <Button key={value} size="sm" variant={filter === value ? 'default' : 'outline'} onClick={() => setFilter(value)}>{value === 'all' ? '全部' : value === 'untagged' ? '未标注' : value === 'reviewed' ? '已标注' : '日期异常'}</Button>)}</section>
      </aside>
    </div>
  </main>;
}
