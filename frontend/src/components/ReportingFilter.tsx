import { useId } from 'react';
import { Label } from '@/components/ui/label';
import type { Selection } from './useReportingOptions';

export function ReportingFilter({
  options,
  names,
  value,
  onChange,
}: {
  options: Selection[];
  names: Record<string, string>;
  value: string;
  onChange: (selection: Selection) => void;
}) {
  const id = useId();

  return (
    <div>
      <Label htmlFor={id}>Period or season</Label>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          const selection = options.find(
            (option) => option.key === event.target.value,
          );
          if (selection) onChange(selection);
        }}
      >
        {options.map((option) => (
          <option key={option.key} value={option.key}>
            {names[option.key] ?? 'Year to date'}
          </option>
        ))}
      </select>
    </div>
  );
}
