export interface IdentificationResult {
  eventId: string;
  visitorId: string | null;
  digest: string;
  /** Repeatable scoped profile code; null when model/font evidence is insufficient. */
  continuityCode?: string | null;
  history?: {visitorFound: boolean; firstSeenAt: string | null; previousSeenAt: string | null};
  origin?: string;
  linkedId?: string | null;
  tags?: Record<string, string>;
  method: 'provisional' | 'inferred' | 'enrolled' | 'remembered' | 'unassigned';
  reason: string;
  createdAt: string;
  expiresAt: string;
  decision: { policy: string; status: string; candidateCount: number; omissions: unknown[] };
  token?: string;
}
export declare function createAgent(options: {publicKey: string; endpoint?: string; mode?: 'resilient' | 'detailed' | 'legacy'}): {
  identify(options?: {remember?: boolean; requestId?: string; linkedId?: string; tags?: Record<string, string>}): Promise<IdentificationResult>;
  forget(): void;
};
