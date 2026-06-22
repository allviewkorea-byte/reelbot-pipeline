import type { Metadata, Viewport } from "next";
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

const SITE_URL = "https://reelbot-pipeline.vercel.app";
const OG_TITLE = "ReelBot — AI 영상 자동화";
const OG_DESC = "AI 영상 자동화 파이프라인 관리 대시보드";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "ReelBot - AI 여행 영상 자동화",
  description: "AI 여행 유튜브 자동화 파이프라인 관리 대시보드",
  manifest: "/manifest.webmanifest",
  openGraph: {
    title: OG_TITLE,
    description: OG_DESC,
    url: SITE_URL,
    siteName: "ReelBot",
    images: ["/og-image.png"],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: OG_TITLE,
    description: OG_DESC,
    images: ["/og-image.png"],
  },
  icons: {
    icon: ["/icon-192.png", "/icon-512.png"],
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: {
    capable: true,
    title: "ReelBot",
    statusBarStyle: "black-translucent",
  },
};

// 다크 네이비(--background: 222 47% 11% = #0f1729). 기존 토큰 값의 hex(신규 토큰 아님).
export const viewport: Viewport = {
  themeColor: "#0f1729",
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
