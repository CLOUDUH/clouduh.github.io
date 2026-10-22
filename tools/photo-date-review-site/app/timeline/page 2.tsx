'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CalendarRange, Copy, Database, ImageOff, Search } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

type Item = { id: string; filename: string; relativePath: string; currentFolder: string; location: string; captureDate: string | null; timelineMismatch: boolean; metadataStatus: string; thumbnail: string | null };
type Manifest = { stats: { items: number; timelineMismatches: number; exactDuplicateGroups: number; visualDuplicateGroups: number; metadataIssues: number }; items: Item[] };

export default function TimelinePage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/timeline/timeline-items.json')
      .then((response) => { if (!response.ok) throw new Error('无法读取时间线数据'); return response.json(); })
      .then(setManifest)
      .catch((reason) => setError(reason instanceof Error ? reason.message : '加载失败'));
  }, []);

  const items = useMemo(() => {
    if (!manifest) return [];
    const value = query.trim().toLowerCase();
    return manifest.items
      .filter((item) => item.location === 'library' && item.timelineMismatch)
      .filter((item) => `${item.filename} ${item.currentFolder} ${item.captureDate ?? ''}`.toLowerCase().includes(value))
      .slice(0, 60);
  }, [manifest, query]);

  if (error) return <main className="grid min-h-screen place-items-center bg-background p-8"><p className="rounded-2xl border bg-card p-6 text-destructive">{error}</p></main>;
  if (!manifest) return <main className="min-h-screen animate-pulse bg-background" />;

  const cards = [
    { label: '全部媒体', value: manifest.stats.items, icon: Database },
    { label: '时间线待核对', value: manifest.stats.timelineMismatches, icon: CalendarRange },
    { label: '重复与相似组', value: manifest.stats.exactDuplicateGroups + manifest.stats.visualDuplicateGroups, icon: Copy },
    { label: '元数据问题', value: manifest.stats.metadataIssues, icon: AlertTriangle },
  ];

  return <main className="min-h-screen bg-background text-foreground">
    <header className="border-b bg-card/80">
      <div className="mx-auto max-w-[1760px] px-4 py-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4"><div><div className="flex items-center gap-2"><CalendarRange className="size-5 text-primary" /><Badge variant="outline">本机私密</Badge></div><h1 className="mt-2 text-3xl font-semibold tracking-tight">记忆时间线整理台</h1><p className="mt-1 text-sm text-muted-foreground">170909—190613 · 先核对错放，再处理重复与日期</p></div><a href="/select" className="text-sm text-muted-foreground hover:text-foreground">返回精选工具</a></div>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, icon: Icon }) => <div key={label} className="rounded-2xl border bg-background/70 p-4"><div className="flex items-center justify-between"><p className="text-sm text-muted-foreground">{label}</p><Icon className="size-4 text-primary" /></div><p className="mt-2 text-3xl font-semibold tabular-nums">{value.toLocaleString()}</p></div>)}</div>
      </div>
    </header>
    <div className="mx-auto max-w-[1760px] p-4 lg:p-8">
      <Tabs defaultValue="timeline">
        <TabsList className="h-10"><TabsTrigger value="timeline" className="px-4">时间线</TabsTrigger><TabsTrigger value="duplicates" className="px-4">重复版本</TabsTrigger><TabsTrigger value="metadata" className="px-4">元数据</TabsTrigger></TabsList>
        <TabsContent value="timeline" className="mt-5">
          <div className="mb-5 flex flex-wrap items-center gap-3"><div className="relative min-w-64 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名、当前文件夹或拍摄日期" className="pl-9" /></div><Badge variant="secondary">当前显示 {items.length} / {manifest.stats.timelineMismatches}</Badge></div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">{items.map((item) => <article key={item.id} className="overflow-hidden rounded-2xl border bg-card"><div className="aspect-[4/3] bg-photo-stage">{item.thumbnail ? <img src={item.thumbnail} alt={item.filename} loading="lazy" className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center"><ImageOff className="text-stone-400" /></div>}</div><div className="p-3"><p className="truncate text-sm font-medium" title={item.filename}>{item.filename}</p><p className="mt-1 truncate text-xs text-muted-foreground">当前：{item.currentFolder}</p><p className="mt-1 font-mono text-[11px] text-primary">{item.captureDate ?? '没有拍摄日期'}</p></div></article>)}</div>
        </TabsContent>
        <TabsContent value="duplicates" className="mt-5 rounded-3xl border border-dashed p-10 text-center text-muted-foreground">重复版本对比正在接入</TabsContent>
        <TabsContent value="metadata" className="mt-5 rounded-3xl border border-dashed p-10 text-center text-muted-foreground">元数据审阅正在接入</TabsContent>
      </Tabs>
    </div>
  </main>;
}
