import { useEffect, useState } from 'react';
import { useServices } from '../services/servicesContext';
import type { ReportFilters, ReportingPeriod } from '../services/types';
import { toErrorMessage } from '../lib/errors';

export interface Selection {
  key: string;
  filters: ReportFilters;
  startDate: string;
  endDate: string;
}

function defaultSelection(): Selection {
  const endDate = new Date().toISOString().slice(0, 10);
  const startDate = `${endDate.slice(0, 4)}-01-01`;
  return {
    key: 'default',
    filters: { startDate, endDate },
    startDate,
    endDate,
  };
}

export function useReportingOptions() {
  const { reporting } = useServices();
  const [options, setOptions] = useState<Selection[]>([defaultSelection()]);
  const [error, setError] = useState('');
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let active = true;
    Promise.all([reporting.periods(), reporting.seasons()])
      .then(([periods, seasons]) => {
        if (!active) return;
        const map = (
          period: ReportingPeriod,
          kind: 'period' | 'season',
        ): Selection => ({
          key: `${kind}:${period.id}`,
          filters:
            kind === 'period'
              ? { periodId: period.id }
              : { startDate: period.startDate, endDate: period.endDate },
          startDate: period.startDate,
          endDate: period.endDate,
        });
        setOptions([
          defaultSelection(),
          ...periods.map((p) => map(p, 'period')),
          ...seasons.map((p) => map(p, 'season')),
        ]);
        setNames(
          Object.fromEntries([
            ...periods.map((p) => [`period:${p.id}`, `Period: ${p.name}`]),
            ...seasons.map((p) => [`season:${p.id}`, `Season: ${p.name}`]),
          ]),
        );
      })
      .catch((reason: unknown) => {
        if (active) setError(toErrorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [reporting]);
  return { options, names, error };
}
