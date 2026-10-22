import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '照片整理工作台',
  description: '在本机整理照片时间线、重复版本、精选与拍摄日期。',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
