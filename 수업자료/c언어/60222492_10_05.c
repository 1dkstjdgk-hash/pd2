#include <stdio.h>
void main(){
	int i =1;
	int num1,num2;
	printf("정수 2개를 입력하시오:");
	scanf("%d %d",&num1,&num2);
	while(i<=100){if(i%num1==0&&i%num2!=0){
		printf("첫 번째 수의 배수지만 두 번째 수의 배수가 아닌 정수:%d\n",i);
	}i++;
		
	}
}
