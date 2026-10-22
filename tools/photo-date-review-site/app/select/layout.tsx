import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '照片精选工作台',
  description: '在本机按文件夹挑选喜欢的照片。',
};

export default function SelectionLayout({ children }: Readonly<{ children: React.ReactNode }>) { return children; }
