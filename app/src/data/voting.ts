export function voteThreshold(boardSize: number): number {
  return Math.ceil((boardSize * 2) / 3);
}

export function voteState(votes: string[], boardSize: number) {
  const threshold = voteThreshold(boardSize);
  const count = votes.length;
  return {
    count,
    threshold,
    state: count >= threshold ? ('passed' as const) : ('open' as const),
  };
}
