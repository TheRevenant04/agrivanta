import type {
  ImportCommitInput,
  ImportCommitResult,
  ImportEntityType,
  ImportPreview,
  ImportServices,
} from '@/services/types';
import type { ServiceRequest } from './farmSetupHttp';
import type { UploadRequest } from './expensePaymentHttp';

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

export function createImportHttp(
  request: ServiceRequest,
  upload: UploadRequest,
): ImportServices {
  return {
    imports: {
      preview: (entityType: ImportEntityType, file: File) =>
        upload<ImportPreview>('/imports/preview', file, true, { entityType }),
      commit: (input: ImportCommitInput) =>
        request<ImportCommitResult>('/imports/commit', body(input), true),
    },
  };
}
