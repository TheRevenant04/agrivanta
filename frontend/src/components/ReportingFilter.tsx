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
  return (
    <label>
      Period or season
      <select
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
    </label>
  );
}
