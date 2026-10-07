export interface IdentificationResult {
  eventId: string;
  visitorId: string | null;
  digest: string;
  method: 'provisional' | 'inferred' | 'enrolled' | 'remembered' | 'unassigned';
  reason: string;
  createdAt: string;
  expiresAt: string;
  decision: { policy: string; status: string; candidateCount: number; omissions: unknown[] };
  token?: string;
}
export declare function createAgent(options: {publicKey: string; endpoint?: string; mode?: 'detailed' | 'legacy'}): {
  identify(options?: {remember?: boolean; requestId?: string}): Promise<IdentificationResult>;
  forget(): void;
};
