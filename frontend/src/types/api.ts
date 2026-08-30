export interface Holding {
  id: number
  node_code: string
  node_name: string
  level: string
  slot: number
  floor: number | null
}

export interface Team {
  code: string
  name: string
  balance: number
  color: string | null
  holdings: Holding[]
}

export interface Me {
  id: number
  username: string
  is_staff: boolean
}

export interface LoginCredentials {
  username: string
  password: string
}
