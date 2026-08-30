/** Deterministic colours for the 48 L1 diamond start nodes. Keep in sync with
 * backend/teams/start_colors.py.
 */
export const START_COUNT = 48

export const START_COLORS = [
  '#d92121',
  '#d9d921',
  '#21d921',
  '#21d9d9',
  '#2121d9',
  '#d921d9',
  '#d93721',
  '#c3d921',
  '#21d937',
  '#21c3d9',
  '#3721d9',
  '#d921c3',
  '#d94d21',
  '#add921',
  '#21d94d',
  '#21add9',
  '#4d21d9',
  '#d921ad',
  '#d96321',
  '#96d921',
  '#21d963',
  '#2196d9',
  '#6321d9',
  '#d92196',
  '#d97921',
  '#80d921',
  '#21d979',
  '#2180d9',
  '#7921d9',
  '#d92180',
  '#d98f21',
  '#6ad921',
  '#21d98f',
  '#216ad9',
  '#8f21d9',
  '#d9216a',
  '#d9a521',
  '#54d921',
  '#21d9a5',
  '#2154d9',
  '#a521d9',
  '#d92154',
  '#d9bb21',
  '#3ed921',
  '#21d9bb',
  '#213ed9',
  '#bb21d9',
  '#d9213e',
]

const START_ID_RE = /^L1_(\d+)$/

export function startIndexFromId(id) {
  const match = START_ID_RE.exec(id)
  if (!match) {
    return null
  }
  const number = Number(match[1])
  if (number % 4 !== 0) {
    return null
  }
  const index = number / 4
  if (index < 0 || index >= START_COUNT) {
    return null
  }
  return index
}

export function colorForStartId(id) {
  const index = startIndexFromId(id)
  return index === null ? null : START_COLORS[index]
}
