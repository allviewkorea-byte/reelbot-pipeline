import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChannelProvider } from "@/components/channels/ChannelProvider";
import { Toaster } from "sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ReelBot - AI 여행 영상 자동화",
  description: "AI 여행 유튜브 자동화 파이프라인 관리 대시보드",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex h-full bg-background text-foreground">
        <ChannelProvider>
          <Sidebar />
          <main className="flex flex-1 flex-col overflow-auto">
            {children}
          </main>
        </ChannelProvider>
        <Toaster position="bottom-right" richColors />
      </body>
    </html>
  );
}
