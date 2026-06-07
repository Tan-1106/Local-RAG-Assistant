export interface ExtractedSseEvents {
  events: string[];
  remainder: string;
}

export function extractSseEvents(buffer: string): ExtractedSseEvents {
  const events: string[] = [];
  let remainder = buffer;
  let separator = remainder.match(/\r?\n\r?\n/);

  while (separator?.index !== undefined) {
    events.push(remainder.slice(0, separator.index));
    remainder = remainder.slice(separator.index + separator[0].length);
    separator = remainder.match(/\r?\n\r?\n/);
  }

  return { events, remainder };
}

export function getSseData(event: string): string {
  return event
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart())
    .join('\n');
}
