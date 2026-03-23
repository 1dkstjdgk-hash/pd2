#include <stdio.h>

void even(){
	printf("1818!");
}

void odd(){
	printf("9797!");
}

void main() {
	int number;
	printf("정수를 입력하시오:");
	scanf("%d", &number);
	if(number % 2 == 0)
		even();
	else
		odd(); 
	
}
