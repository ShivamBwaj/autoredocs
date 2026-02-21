package com.example;

/**
 * A simple calculator class.
 *
 * Supports basic arithmetic operations.
 */
public class Calculator {
    private int precision;

    /**
     * Initialize with a given decimal precision.
     */
    public Calculator(int precision) {
        this.precision = precision;
    }

    /**
     * Add two numbers.
     */
    public double add(double a, double b) {
        return a + b;
    }

    /**
     * Divide a by b.
     *
     * @param a the dividend
     * @param b the divisor
     * @throws ArithmeticException if b is zero
     */
    public double divide(double a, double b) {
        if (b == 0) {
            throw new ArithmeticException("Cannot divide by zero");
        }
        return a / b;
    }

    /**
     * Check if a number is positive.
     */
    public static boolean isPositive(double n) {
        return n > 0;
    }
}

/**
 * Represents a user in the system.
 */
public interface User {
    String getName();
    String getEmail();
}

/**
 * Status of a build operation.
 */
public enum BuildStatus {
    PENDING,
    RUNNING,
    SUCCESS,
    FAILED;
}
