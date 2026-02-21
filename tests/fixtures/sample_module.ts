/**
 * Sample TypeScript module for testing the TS parser.
 *
 * Contains functions, classes, and interfaces.
 */

import { EventEmitter } from "events";

/**
 * Greet the given user by name.
 */
export function greet(name: string, excited: boolean = false): string {
    const suffix = excited ? "!" : ".";
    return `Hello, ${name}${suffix}`;
}

/**
 * Add two numbers together.
 */
export const add = (a: number, b: number): number => {
    return a + b;
};

export async function fetchData(url: string, timeout: number = 30): Promise<Record<string, unknown>> {
    return { url, timeout };
}

/**
 * Represents a user in the system.
 */
export class User {
    name: string;
    email: string;
    age?: number;

    constructor(name: string, email: string, age?: number) {
        this.name = name;
        this.email = email;
        this.age = age;
    }

    /**
     * Return a formatted string with all user info.
     */
    fullInfo(): string {
        const parts = [`${this.name} <${this.email}>`];
        if (this.age !== undefined) {
            parts.push(`(age ${this.age})`);
        }
        return parts.join(" ");
    }

    isAdult(): boolean {
        return this.age !== undefined && this.age >= 18;
    }
}

/**
 * A data transfer object interface.
 */
export interface UserDTO {
    name: string;
    email: string;
    age?: number;
}

export type UserRole = "admin" | "editor" | "viewer";
