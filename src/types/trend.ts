export type VideoFormat = 'shorts' | 'long';

export interface TrendInsight {
  channelId: string;
  category: string;
  format: VideoFormat;
  analyzedAt: string;

  avgVideoLengthSec: number;
  avgTitleLength: number;
  powerWords: { word: string; count: number }[];

  descriptionPattern: {
    first150Keywords: string[];
    hookStructure: string;
  };

  tagsByCategory: {
    primary: string[];
    variants: string[];
    competitor: string[];
    broad: string[];
    niche: string[];
  };

  hookPatterns: string[];
  popularUploadHours: number[];

  commentInsights: {
    sentiment: { positive: number; negative: number; neutral: number };
    faqs: string[];
    contentIdeas: string[];
  };
}

export interface TrendSettings {
  enabled: boolean;
  keywords: string[];
  categories: string[];
  formats: VideoFormat[];
  schedule: 'daily' | 'manual';
  lastAnalyzedAt?: string;
}
